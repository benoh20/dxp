# powerbuilder/chat/agents/precincts.py
import logging
import os
from typing import List

import pandas as pd
import requests
from langchain_openai import ChatOpenAI

from ..utils.census_vars import VOTER_DEMOGRAPHICS
from ..utils.data_fetcher import DataFetcher
from ..utils.district_standardizer import GeographyStandardizer
from .state import AgentState

logger = logging.getLogger(__name__)


class PrecinctsAgent:
    """
    The Spatial Architect: Maps Census demographics onto Voting Precincts
    using dasymetric reaggregation (weighting).

    Crosswalk files (built by crosswalk_builder.py) map Census block groups to
    precinct boundaries with areal interpolation weights. This agent fetches
    block-group-level Census data, applies those weights, and reaggregates to
    the precinct level.
    """

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _get_district_bg_geoids(
        state_fips: str, district_id: str, district_type: str
    ) -> set:
        """
        Returns the set of 12-character block group GEOIDs that fall within
        the target district, using the Census API nested geography predicate.

        Returns an empty set on failure so the caller can proceed without
        district filtering rather than crashing.
        """
        if district_type == "congressional":
            dist_num = district_id[len(state_fips):]          # "5107"[2:] = "07"
            in_pred = f"state:{state_fips} congressional district:{dist_num}"
        elif district_type == "state_senate":
            dist_num = district_id[len(state_fips) + 1:]      # strip "S" prefix
            in_pred = f"state:{state_fips} state legislative district (upper chamber):{dist_num}"
        elif district_type == "state_house":
            dist_num = district_id[len(state_fips) + 1:]      # strip "H" prefix
            in_pred = f"state:{state_fips} state legislative district (lower chamber):{dist_num}"
        else:
            logger.warning(f"Unrecognised district_type '{district_type}'; skipping district filter.")
            return set()

        try:
            response = requests.get(
                "https://api.census.gov/data/2022/acs/acs5",
                params={
                    "get": "NAME",
                    "for": "block group:*",
                    "in": in_pred,
                    "key": os.getenv("CENSUS_API_KEY"),
                },
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()
            headers = data[0]
            geoids = set()
            for row in data[1:]:
                r = dict(zip(headers, row))
                # Reconstruct the 12-char GEOID: state(2)+county(3)+tract(6)+bg(1)
                geoid = (
                    r.get("state", "").zfill(2)
                    + r.get("county", "").zfill(3)
                    + r.get("tract", "").zfill(6)
                    + r.get("block group", "")
                )
                geoids.add(geoid)
            logger.info(f"  District {district_id}: {len(geoids)} block groups in scope.")
            return geoids
        except Exception as e:
            logger.warning(
                f"  Could not fetch BG list for district {district_id}: {e}. "
                "Proceeding without district filter."
            )
            return set()

    @staticmethod
    def _parse_precinct_name(precinct_geoid: str) -> str:
        """
        Extracts the human-readable name from the full precinct GEOID string.

        Input:  "01001-10 JONES COMM_ CTR_"
        Output: "JONES COMM_ CTR_"
        """
        parts = precinct_geoid.split(" ", 1)
        return parts[1].strip() if len(parts) > 1 else precinct_geoid

    # ------------------------------------------------------------------
    # Core method
    # ------------------------------------------------------------------

    @staticmethod
    def get_top_precincts(
        state_fips: str,
        district_id: str,
        district_type: str = "congressional",
        metrics: List[str] = None,
        top_n: int = 20,
    ) -> list:
        """
        Returns the top N precincts ranked by the first metric in the list.

        Args:
            state_fips:    Zero-padded 2-digit FIPS string, e.g. "51"
            district_id:   GEOID string, e.g. "5107" for VA-07
            district_type: "congressional" | "state_senate" | "state_house"
            metrics:       List of friendly Census variable names from census_vars.py,
                           e.g. ["total_cvap", "black", "hispanic"].
                           Raw Census codes (e.g. "B01001_001E") also accepted.
            top_n:         Number of top precincts to return

        Returns a list of dicts with a predictable schema:
            {
                "precinct_geoid":      str,   # full GEOID from TopoJSON
                "precinct_name":       str,   # human-readable name parsed from GEOID
                "<metric_1>":          float, # weighted reaggregated value
                ...
                "approximate_boundary": bool  # True when official_boundary is False
            }
        """
        if metrics is None:
            metrics = ["total_cvap"]

        # Translate friendly names to Census API codes for column lookup
        # e.g. "total_cvap" → "B29001_001E", raw codes pass through unchanged
        metric_to_code = {m: VOTER_DEMOGRAPHICS.get(m, m) for m in metrics}

        # 1. Fetch Census block-group data for all metrics
        raw_bg_data = DataFetcher.get_census_data(state_fips, metrics, geo_level="precinct")
        if not raw_bg_data or "error" in raw_bg_data[0]:
            logger.error(f"Census fetch failed: {raw_bg_data}")
            return [{"error": f"Census API failure: {raw_bg_data[0].get('error') if raw_bg_data else 'no data'}"}]

        bg_df = pd.DataFrame(raw_bg_data)

        # Construct the 12-char bg_geoid from the component Census API fields.
        # The Census API returns state, county, tract, block group as separate columns —
        # there is no pre-built GEOID column in the response.
        bg_df["bg_geoid"] = (
            bg_df["state"].str.zfill(2)
            + bg_df["county"].str.zfill(3)
            + bg_df["tract"].str.zfill(6)
            + bg_df["block group"]
        )

        # 2. Filter to block groups within the target district before the crosswalk merge
        district_bg_geoids = PrecinctsAgent._get_district_bg_geoids(
            state_fips, district_id, district_type
        )
        if district_bg_geoids:
            bg_df = bg_df[bg_df["bg_geoid"].isin(district_bg_geoids)].copy()
            if bg_df.empty:
                logger.warning(f"No block groups matched district filter for {district_id}.")
                return [{"error": f"No Census block groups found within district {district_id}."}]
        else:
            logger.warning("District filter unavailable; using all state block groups.")

        # 3. Load the crosswalk (built by crosswalk_builder.py)
        crosswalk_path = f"data/crosswalks/{state_fips}_bg_to_precinct.csv"
        try:
            crosswalk = pd.read_csv(crosswalk_path)
        except FileNotFoundError:
            return [{"error": f"Crosswalk missing for state {state_fips}. "
                              "Run crosswalk_builder.build_crosswalk() first."}]

        # Normalise official_boundary to bool (CSV reads it as string)
        crosswalk["official_boundary"] = (
            crosswalk["official_boundary"].astype(str).str.lower() == "true"
        )

        # 4. Merge block group Census data with crosswalk
        # Core dasymetric logic — do not change
        merged = bg_df.merge(crosswalk, on="bg_geoid")

        if merged.empty:
            return [{"error": f"Crosswalk merge produced no rows for district {district_id}. "
                              "Verify that the crosswalk was built for this state."}]

        # 5. Apply dasymetric weights per metric and reaggregate by precinct
        # weighted_value = block_group_value * (intersection_area / bg_total_area)
        # Do not change this logic
        for friendly_name, census_code in metric_to_code.items():
            if census_code in merged.columns:
                merged[f"weighted_{friendly_name}"] = (
                    pd.to_numeric(merged[census_code], errors="coerce").fillna(0)
                    * merged["weight"]
                )
            else:
                logger.warning(f"Column '{census_code}' not found in Census data; skipping metric '{friendly_name}'.")

        weighted_cols = [f"weighted_{m}" for m in metrics if f"weighted_{m}" in merged.columns]

        # Aggregate weighted values by precinct
        precinct_totals = merged.groupby("precinct_geoid")[weighted_cols].sum()

        # Determine boundary quality per precinct:
        # approximate_boundary = True if ANY contributing BG has official_boundary=False
        boundary_flags = (
            merged.groupby("precinct_geoid")["official_boundary"]
            .all()
            .rename("all_official")
        )
        precinct_totals = precinct_totals.join(boundary_flags)
        precinct_totals["approximate_boundary"] = ~precinct_totals["all_official"].fillna(False)
        precinct_totals = precinct_totals.drop(columns=["all_official"])

        # 6. Rank by first metric and take top N
        primary_col = f"weighted_{metrics[0]}"
        if primary_col in precinct_totals.columns:
            precinct_totals = precinct_totals.sort_values(primary_col, ascending=False)

        top_targets = precinct_totals.head(top_n).reset_index()

        # 7. Build standardised output schema
        results = []
        for _, row in top_targets.iterrows():
            record = {
                "precinct_geoid": row["precinct_geoid"],
                "precinct_name":  PrecinctsAgent._parse_precinct_name(row["precinct_geoid"]),
            }
            for metric in metrics:
                wcol = f"weighted_{metric}"
                if wcol in row.index:
                    record[metric] = round(float(row[wcol]), 2)
            record["approximate_boundary"] = bool(row.get("approximate_boundary", False))
            results.append(record)

        return results

    # ------------------------------------------------------------------
    # LangGraph node wrapper
    # ------------------------------------------------------------------

    @staticmethod
    def run(state: AgentState) -> dict:
        """
        LangGraph node wrapper. Extracts precinct targeting parameters from
        the user's query via LLM, calls get_top_precincts(), and writes
        results to AgentState.
        """
        llm = ChatOpenAI(
            model="gpt-4o",
            temperature=0,
            openai_api_key=os.environ["OPENAI_API_KEY"],
        )

        extraction_prompt = f"""
Extract precinct targeting parameters from this query. Return ONLY these lines, no extra text.

Query: "{state['query']}"

STATE: [full state name or abbreviation, e.g. "Virginia" or "VA"]
DISTRICT_TYPE: [congressional | state_senate | state_house]
DISTRICT_NUM: [integer district number]
METRICS: [comma-separated Census variable names from this list: total_cvap, total_population, black, hispanic, white, median_income, poverty_total, unemployed — choose what is relevant to the query]
TOP_N: [integer number of precincts to return, default 20]
"""
        try:
            raw = llm.invoke(extraction_prompt).content.strip()
        except Exception as e:
            return {
                "errors":        [f"PrecinctsAgent: LLM extraction failed — {e}"],
                "active_agents": ["precincts"],
            }

        params = {}
        for line in raw.splitlines():
            if ":" in line:
                key, _, val = line.partition(":")
                params[key.strip().upper()] = val.strip().strip('"')

        # Resolve state FIPS
        state_name = params.get("STATE", "")
        state_fips = GeographyStandardizer.STATE_FIPS.get(state_name.lower())
        if not state_fips:
            return {
                "errors":        [f"PrecinctsAgent: Could not resolve state FIPS for '{state_name}'."],
                "active_agents": ["precincts"],
            }

        district_type = params.get("DISTRICT_TYPE", "congressional").lower()
        metrics = [m.strip() for m in params.get("METRICS", "total_cvap").split(",") if m.strip()]

        try:
            dist_num = int(params.get("DISTRICT_NUM", 0))
            top_n    = int(params.get("TOP_N", 20))
        except ValueError:
            dist_num = 0
            top_n    = 20

        # Build GEOID for the target district
        geoid = GeographyStandardizer.convert_to_geoid(state_name, dist_num, district_type)
        if isinstance(geoid, dict):
            return {
                "errors":        [f"PrecinctsAgent: {geoid.get('error')}"],
                "active_agents": ["precincts"],
            }

        results = PrecinctsAgent.get_top_precincts(
            state_fips, geoid, district_type, metrics, top_n
        )

        # Surface any errors returned from get_top_precincts
        if results and "error" in results[0]:
            return {
                "errors":        [f"PrecinctsAgent: {results[0]['error']}"],
                "active_agents": ["precincts"],
            }

        return {
            "structured_data": [{
                "agent":         "precincts",
                # Geographic context written here so downstream agents (win_number,
                # messaging, cost_calculator) can read it without re-extracting from query
                "state_fips":    state_fips,
                "district_type": district_type,
                "district_id":   geoid,
                "precincts":     results,
            }],
            "active_agents": ["precincts"],
        }
