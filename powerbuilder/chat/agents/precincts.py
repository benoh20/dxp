# powerbuilder/chat/agents/precincts.py
import logging
import os
from typing import List

from dotenv import load_dotenv
load_dotenv()

import pandas as pd
import requests
from langchain_openai import ChatOpenAI

from ..utils.census_vars import VOTER_DEMOGRAPHICS, MULTI_VAR_METRICS, TRACT_ONLY_METRICS
from ..utils.data_fetcher import DataFetcher
from ..utils.district_standardizer import GeographyStandardizer
from ..utils.storage import file_exists, read_dataframe
from .state import AgentState

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Demographic targeting configuration
# ---------------------------------------------------------------------------

# Maps AgentState.demographic_intent → primary metrics passed to get_top_precincts().
_DEMOGRAPHIC_METRICS: dict[str, list[str]] = {
    "youth":         ["youth_vap", "college_enrolled"],
    "hispanic":      ["hispanic_pop"],
    "black":         ["black_pop"],
    "aapi":          ["aapi"],
    "native":        ["native_pop"],
    "senior":        ["senior_vap"],
    "educated":      ["graduate_educated"],
    "working_class": ["no_hs_diploma", "some_college"],
    "low_income":    ["poverty_pop"],
    "high_income":   ["median_income"],
    "immigrant":     ["foreign_born_pop"],
    "veteran":       ["veteran_pop"],
    "suburban":      ["owner_pop"],
    "renter":        ["renter_pop"],
    "default":       ["total_vap"],
}

# Human-readable explanation written into structured_data["demographic_profile"].
_DEMOGRAPHIC_PROFILES: dict[str, str] = {
    "youth": (
        "Targeting precincts with high concentrations of voters aged 18-29 and college "
        "enrollment. youth_vap sums B01001_007-011E and B01001_031-035E (18-29 male and "
        "female); college_enrolled uses B14001_005E."
    ),
    "hispanic": (
        "Targeting precincts with high Hispanic/Latino population concentrations "
        "(B03003_003E). Note: total population, not CVAP — citizenship rates vary."
    ),
    "black": (
        "Targeting precincts with high Black/African American population concentrations "
        "(B02001_003E). Note: total population, not CVAP."
    ),
    "aapi": (
        "Targeting precincts with high Asian American and Pacific Islander population "
        "concentrations. Combines Asian alone (B02001_005E) and Native Hawaiian/Pacific "
        "Islander alone (B02001_006E)."
    ),
    "native": (
        "Targeting precincts with high American Indian and Alaska Native population "
        "concentrations (B02001_004E). Note: total population, not CVAP."
    ),
    "senior": (
        "Targeting precincts with high concentrations of voters aged 65 and older. "
        "senior_vap sums B01001_020-025E (male 65+) and B01001_044-049E (female 65+)."
    ),
    "educated": (
        "Targeting precincts with high concentrations of college and graduate degree holders. "
        "graduate_educated combines bachelor's (B15003_022E) with master's, professional, "
        "and doctoral degrees (B15003_023-025E). Uses tract-level data — less granular than "
        "block-group targeting."
    ),
    "working_class": (
        "Targeting precincts with high concentrations of working-class voters without "
        "four-year degrees. no_hs_diploma sums B15003_002-016E; some_college sums "
        "B15003_019-021E. Both use tract-level data — less granular than block-group targeting."
    ),
    "low_income": (
        "Targeting precincts with high concentrations of low-income households "
        "(B17001_002E — households below the federal poverty line)."
    ),
    "high_income": (
        "Targeting precincts with high median household income (B19013_001E) — "
        "for donor prospecting and persuasion targeting in affluent areas."
    ),
    "immigrant": (
        "Targeting precincts with high concentrations of foreign-born and naturalized "
        "citizen populations (B05002_013E — foreign-born). Note: not all foreign-born "
        "residents are eligible voters."
    ),
    "veteran": (
        "Targeting precincts with high concentrations of veteran and military-connected "
        "voters (B21001_002E — civilian veterans 18+)."
    ),
    "suburban": (
        "Targeting precincts with high homeownership rates (B25003_002E — owner-occupied "
        "housing units) as a proxy for suburban and exurban voter populations."
    ),
    "renter": (
        "Targeting precincts with high renter-occupied housing (B25003_003E) — proxy for "
        "urban and transient populations, including young voters and recent movers."
    ),
    "default": (
        "No demographic targeting specified. Ranking precincts by total voting-age population "
        "(VAP from 2020 Decennial PL94-171) — the broadest measure of the resident voter universe."
    ),
}


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

        Congressional districts are intentionally excluded from this Census API
        call. The ACS5 API only resolves block groups within the standard
        geographic hierarchy (state → county → tract → block group); congressional
        districts are not part of that hierarchy, so passing
        `in=state:XX congressional district:XX` with `for=block group:*` returns
        a 400 error. For congressional districts, district filtering happens
        spatially via the crosswalk file (built by crosswalk_builder.py) — either
        the district-specific crosswalk already scopes to the correct BGs, or the
        full-state crosswalk is intersected with precinct boundaries that lie within
        the district. This function returns an empty set for congressional so the
        caller falls through to that crosswalk-based path.

        Returns an empty set on failure so the caller can proceed without
        district filtering rather than crashing.
        """
        # The Census API does not support congressional district as a parent geography
        # for block groups. Return early and let the crosswalk handle district scoping.
        if district_type == "congressional":
            return set()

        if district_type == "state_senate":
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

    @staticmethod
    def _compute_tract_education_weights(
        state_fips: str,
        edu_metrics: list,
        crosswalk: "pd.DataFrame",
    ) -> "pd.DataFrame | None":
        """
        Fetches B15003 education variables at Census tract level (ACS5 block-group
        limitation) and derives tract→precinct weights by summing the existing
        bg→precinct crosswalk weights up to the tract level.

        Returns a DataFrame indexed by precinct_geoid with weighted_<metric> columns,
        or None on failure. Core dasymetric logic is not used here — this is a
        simplified areal-weight approach applied at tract granularity.
        """
        # Expand multi-var education metrics into component friendly names
        component_names: list = []
        for m in edu_metrics:
            if m in MULTI_VAR_METRICS:
                for c in MULTI_VAR_METRICS[m]:
                    if c not in component_names:
                        component_names.append(c)
            elif m not in component_names:
                component_names.append(m)

        # Resolve component friendly names to Census codes (deduplicated)
        comp_to_code = {c: VOTER_DEMOGRAPHICS.get(c, c) for c in component_names}
        census_codes = list(dict.fromkeys(comp_to_code.values()))

        if not census_codes:
            return None

        try:
            response = requests.get(
                "https://api.census.gov/data/2022/acs/acs5",
                params={
                    "get": f"NAME,{','.join(census_codes)}",
                    "for": "tract:*",
                    "in":  f"state:{state_fips}",
                    "key": os.getenv("CENSUS_API_KEY"),
                },
                timeout=45,
            )
            response.raise_for_status()
            data    = response.json()
            headers = data[0]
            tract_df = pd.DataFrame(data[1:], columns=headers)
            tract_df["tract_geoid"] = (
                tract_df["state"].str.zfill(2)
                + tract_df["county"].str.zfill(3)
                + tract_df["tract"].str.zfill(6)
            )
            for code in census_codes:
                if code in tract_df.columns:
                    tract_df[code] = pd.to_numeric(tract_df[code], errors="coerce").fillna(0)
        except Exception as e:
            logger.warning(f"  Tract-level education data fetch failed: {e}")
            return None

        # Build synthetic columns for multi-var education metrics in tract_df
        for m in edu_metrics:
            if m in MULTI_VAR_METRICS:
                comp_codes = [VOTER_DEMOGRAPHICS.get(c, c) for c in MULTI_VAR_METRICS[m]]
                avail      = [c for c in comp_codes if c in tract_df.columns]
                if avail:
                    tract_df[m] = tract_df[avail].sum(axis=1)
            elif m in VOTER_DEMOGRAPHICS and VOTER_DEMOGRAPHICS[m] in tract_df.columns:
                tract_df[m] = tract_df[VOTER_DEMOGRAPHICS[m]]

        # Aggregate crosswalk from BG→precinct to tract→precinct by summing weights
        cw = crosswalk.copy()
        cw["tract_geoid"] = cw["bg_geoid"].str[:11]
        tract_weights = (
            cw.groupby(["tract_geoid", "precinct_geoid"])["weight"]
            .sum()
            .reset_index()
            .rename(columns={"weight": "tract_weight"})
        )

        edu_cols = [m for m in edu_metrics if m in tract_df.columns]
        if not edu_cols:
            logger.warning("  No education columns available in tract data after expansion.")
            return None

        merged = tract_weights.merge(
            tract_df[["tract_geoid"] + edu_cols],
            on="tract_geoid",
            how="left",
        )
        for m in edu_cols:
            merged[f"weighted_{m}"] = merged[m].fillna(0) * merged["tract_weight"]

        weighted_cols = [f"weighted_{m}" for m in edu_cols]
        return merged.groupby("precinct_geoid")[weighted_cols].sum()

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
        combined_primary_metrics: List[str] = None,
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
            metrics = ["total_vap"]

        # Always include total_vap so every output row carries the full VAP denominator.
        # Append rather than prepend so metrics[0] stays the caller's primary sort metric.
        if "total_vap" not in metrics:
            metrics = list(metrics) + ["total_vap"]

        # Split into block-group-available metrics and tract-only education metrics.
        # B15003 (educational attainment) is not available at block group resolution
        # in ACS5; those metrics are handled by a separate tract-level path below.
        bg_metrics  = [m for m in metrics if m not in TRACT_ONLY_METRICS]
        edu_metrics = [m for m in metrics if m in TRACT_ONLY_METRICS]

        # Expand BG multi-variable metrics into their leaf component friendly names.
        # Composite names (e.g. "youth_vap") must never appear in the Census API
        # request — the API only accepts real variable codes like B01001_007E.
        # Composite names are recovered in step 3 after the fetch, when component
        # columns are summed into a synthetic column and metric_to_code is updated.
        fetch_metrics: list = []
        for m in bg_metrics:
            if m in MULTI_VAR_METRICS:
                for comp in MULTI_VAR_METRICS[m]:
                    if comp not in fetch_metrics:
                        fetch_metrics.append(comp)
            elif m not in fetch_metrics:
                fetch_metrics.append(m)

        # Translate leaf friendly names to Census API codes for column lookup.
        # e.g. "hispanic_pop" → "B03003_003E", raw codes pass through unchanged.
        # Composite metric names are absent from fetch_metrics so they cannot
        # appear here and cannot leak into the Census API URL.
        metric_to_code = {m: VOTER_DEMOGRAPHICS.get(m, m) for m in fetch_metrics}

        # Some metrics are crosswalk-native: their values come from columns already
        # present in the crosswalk CSV (built by crosswalk_builder.py) rather than
        # fetched from the Census ACS API. "vap" → "bg_vap" is the primary example.
        # Sending these codes to the Census API would return a 400 error.
        CROSSWALK_NATIVE_CODES = {"bg_vap"}
        acs_metrics = [m for m in fetch_metrics if metric_to_code.get(m) not in CROSSWALK_NATIVE_CODES]
        # Always fetch at least one ACS variable so we have the BG geography columns
        if not acs_metrics:
            acs_metrics = ["total_population"]

        # 1. Fetch Census block-group data for ACS metrics
        raw_bg_data = DataFetcher.get_census_data(state_fips, acs_metrics, geo_level="precinct")
        if not raw_bg_data or "error" in raw_bg_data[0]:
            logger.error(f"Census fetch failed: {raw_bg_data}")
            return {"error": f"Census API failure: {raw_bg_data[0].get('error') if raw_bg_data else 'no data'}"}

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
                return {"error": f"No Census block groups found within district {district_id}."}
        else:
            logger.warning("District filter unavailable; using all state block groups.")

        # 3. Build synthetic columns for BG-level multi-var metrics.
        # Sum component Census code columns into a single column (e.g. "youth_vap")
        # so the dasymetric weighting step treats it like any other ACS variable.
        # Education multi-var metrics are excluded here — they use the tract path below.
        for mv_name, components in MULTI_VAR_METRICS.items():
            if mv_name in bg_metrics:
                comp_codes = [VOTER_DEMOGRAPHICS.get(c, c) for c in components]
                available  = [c for c in comp_codes if c in bg_df.columns]
                if available:
                    bg_df[mv_name] = (
                        bg_df[available].apply(pd.to_numeric, errors="coerce").fillna(0).sum(axis=1)
                    )
                    metric_to_code[mv_name] = mv_name  # point weighting step at the synthetic column
                else:
                    logger.warning(f"No component columns found for multi-var metric '{mv_name}'; skipping.")

        # 4. Load the crosswalk (built by crosswalk_builder.py).
        # Try district-specific crosswalk first (built with district_id arg); these
        # contain only BGs and precincts within the target district and give correct
        # results without relying on the Census API's unsupported BG-by-CD geography.
        # Fall back to the full-state crosswalk when no district-specific file exists.
        # Force bg_geoid to str: pandas auto-casts 12-digit GEOIDs to int64,
        # which would break the merge with bg_df where bg_geoid is always a string.
        district_crosswalk = f"data/crosswalks/{state_fips}_{district_id}_bg_to_precinct.csv"
        state_crosswalk    = f"data/crosswalks/{state_fips}_bg_to_precinct.csv"
        crosswalk_path     = district_crosswalk if file_exists(district_crosswalk) else state_crosswalk
        if crosswalk_path == district_crosswalk:
            logger.info(f"  Using district-specific crosswalk: {crosswalk_path}")
        else:
            logger.info(f"  District crosswalk not found; using state-level: {crosswalk_path}")
        try:
            crosswalk = read_dataframe(crosswalk_path, dtype={"bg_geoid": str})
        except FileNotFoundError:
            return {"error": f"Crosswalk missing for state {state_fips}. "
                             "Run crosswalk_builder.build_crosswalk() first."}

        # Normalise official_boundary to bool (CSV reads it as string)
        crosswalk["official_boundary"] = (
            crosswalk["official_boundary"].astype(str).str.lower() == "true"
        )

        # 5. Merge block group Census data with crosswalk
        # Core dasymetric logic — do not change
        merged = bg_df.merge(crosswalk, on="bg_geoid")

        if merged.empty:
            return {"error": f"Crosswalk merge produced no rows for district {district_id}. "
                             "Verify that the crosswalk was built for this state."}

        # 6. Apply dasymetric weights per metric and reaggregate by precinct
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

        # Use bg_metrics (not full metrics) — edu metric weighted cols won't be in merged
        weighted_cols = [f"weighted_{m}" for m in bg_metrics if f"weighted_{m}" in merged.columns]

        # Aggregate weighted values by precinct.
        # When only education metrics were requested, bg_metrics is empty so we scaffold
        # an empty precinct index from the crosswalk to join education results onto.
        if weighted_cols:
            precinct_totals = merged.groupby("precinct_geoid")[weighted_cols].sum()
        else:
            precinct_totals = (
                merged[["precinct_geoid"]].drop_duplicates().set_index("precinct_geoid")
            )

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

        # 6b. Tract-level education metrics (B15003 — not available at block group in ACS5).
        # Fetches tract data, derives tract→precinct weights from the crosswalk, and joins
        # the resulting weighted columns into precinct_totals. Core dasymetric logic unchanged.
        if edu_metrics:
            logger.warning(
                "  Education metrics (B15003) are available at Census tract level only in ACS5. "
                "Applying simplified tract→precinct areal weighting — results are less granular "
                "than block-group targeting."
            )
            edu_data = PrecinctsAgent._compute_tract_education_weights(
                state_fips, edu_metrics, crosswalk
            )
            if edu_data is not None:
                precinct_totals = precinct_totals.join(edu_data, how="left")
                for m in edu_metrics:
                    col = f"weighted_{m}"
                    if col in precinct_totals.columns:
                        precinct_totals[col] = precinct_totals[col].fillna(0)
            else:
                logger.warning("  Tract-level education weighting failed; education metrics will be absent from output.")

        # 6c. Combined targeting metric (multi-demographic queries).
        # Sum the primary weighted column from each demographic group so the sort
        # reflects the union of targets rather than either group alone.
        if combined_primary_metrics:
            avail_combined = [
                f"weighted_{m}" for m in combined_primary_metrics
                if f"weighted_{m}" in precinct_totals.columns
            ]
            if avail_combined:
                precinct_totals["weighted_combined_target"] = precinct_totals[avail_combined].sum(axis=1)

        use_combined_target = "weighted_combined_target" in precinct_totals.columns

        # 7. Rank by combined target (multi-demo) or primary metric (single demo)
        if use_combined_target:
            sort_col = "weighted_combined_target"
        elif f"weighted_{metrics[0]}" in precinct_totals.columns:
            sort_col = f"weighted_{metrics[0]}"
        else:
            sort_col = None

        if sort_col:
            precinct_totals = precinct_totals.sort_values(sort_col, ascending=False)

        # Count total unique precincts in crosswalk before truncating to top_n.
        # Used for data quality check below.
        total_precinct_count = len(precinct_totals)

        top_targets = precinct_totals.head(top_n).reset_index()

        # 8. Build standardised output schema
        results = []
        for _, row in top_targets.iterrows():
            record = {
                "precinct_geoid": row["precinct_geoid"],
                "precinct_name":  PrecinctsAgent._parse_precinct_name(row["precinct_geoid"]),
            }
            # User-requested metrics (total_vap gets its own standardised key below)
            for metric in metrics:
                if metric == "total_vap":
                    continue
                wcol = f"weighted_{metric}"
                if wcol in row.index:
                    record[metric] = round(float(row[wcol]), 2)

            # Always-present targeting columns
            total_vap_val = float(row.get("weighted_total_vap", 0) or 0)
            if use_combined_target:
                target_val = float(row.get("weighted_combined_target", 0) or 0)
            else:
                target_val = float(row.get(f"weighted_{metrics[0]}", 0) or 0)

            record["total_vap"]              = round(total_vap_val, 2)
            record["target_demographic_vap"] = round(target_val, 2)
            record["target_demographic_pct"] = (
                round(target_val / total_vap_val * 100, 2) if total_vap_val > 0 else 0.0
            )
            record["penetration_rate"] = (
                round(target_val / total_vap_val, 4) if total_vap_val > 0 else 0.0
            )
            record["approximate_boundary"] = bool(row.get("approximate_boundary", False))
            results.append(record)

        # 9. Data quality check: fewer than 100 precincts suggests ward/municipality-level
        # granularity rather than individual polling-precinct granularity.
        data_quality_note = None
        if total_precinct_count < 100:
            data_quality_note = (
                "Precinct data may be reporting at ward or municipality level rather than "
                "individual polling precinct level for this state. Targeting results reflect "
                "broader geographic units and may be less granular than expected."
            )
            logger.warning(
                f"  Data quality: only {total_precinct_count} precincts in crosswalk for "
                f"district {district_id} — results may reflect ward/municipality-level units."
            )

        return {
            "precincts":          results,
            "precinct_count":     total_precinct_count,
            "data_quality_note":  data_quality_note,
            "tract_fallback_used": bool(edu_metrics),
        }

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

        # Demographic intent is set by intent_router_node in manager.py via a keyword
        # scan of the query — no extra LLM call required. It overrides whatever METRICS
        # the LLM extracted, ensuring the targeting metric always matches the user's ask.
        # Combined intents (e.g. "black+hispanic") are joined with "+" and split here.
        demographic_intent = (state.get("demographic_intent") or "default").lower()
        intents = demographic_intent.split("+") if "+" in demographic_intent else [demographic_intent]

        # Collect the union of metrics across all matched intents (order preserved, deduplicated)
        metrics: list = []
        combined_primary_metrics: list = []
        for intent in intents:
            intent_metrics = _DEMOGRAPHIC_METRICS.get(intent, _DEMOGRAPHIC_METRICS["default"])
            primary = intent_metrics[0] if intent_metrics else None
            if primary and primary not in combined_primary_metrics:
                combined_primary_metrics.append(primary)
            for m in intent_metrics:
                if m not in metrics:
                    metrics.append(m)

        if len(intents) > 1:
            demographic_profile = " | ".join(
                _DEMOGRAPHIC_PROFILES[i] for i in intents if i in _DEMOGRAPHIC_PROFILES
            )
        else:
            demographic_profile = _DEMOGRAPHIC_PROFILES.get(demographic_intent, _DEMOGRAPHIC_PROFILES["default"])
            combined_primary_metrics = None  # single intent: no synthetic combined column needed

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

        output = PrecinctsAgent.get_top_precincts(
            state_fips, geoid, district_type, metrics, top_n,
            combined_primary_metrics=combined_primary_metrics,
        )

        # Error path: get_top_precincts returns {"error": "..."} on failure
        if "error" in output:
            return {
                "errors":        [f"PrecinctsAgent: {output['error']}"],
                "active_agents": ["precincts"],
            }

        precincts           = output["precincts"]
        precinct_count      = output["precinct_count"]
        data_quality_note   = output["data_quality_note"]
        tract_fallback_used = output.get("tract_fallback_used", False)

        state_update: dict = {
            "structured_data": [{
                "agent":         "precincts",
                # Geographic context written here so downstream agents (win_number,
                # messaging, cost_calculator) can read it without re-extracting from query
                "state_fips":    state_fips,
                "district_type": district_type,
                "district_id":   geoid,
                "precincts":     precincts,
                "precinct_count": precinct_count,
                "demographic_profile": {
                    "intent":      demographic_intent,
                    "metrics":     metrics,
                    "explanation": demographic_profile,
                },
            }],
            "active_agents": ["precincts"],
        }

        if data_quality_note:
            state_update["structured_data"][0]["data_quality_note"] = data_quality_note
            state_update["errors"] = [f"PrecinctsAgent: {data_quality_note}"]

        if tract_fallback_used:
            state_update["structured_data"][0]["tract_fallback_note"] = (
                "College enrollment (B14001_005E) and/or education attainment (B15003) "
                "data were sourced from Census tract level (ACS5 block-group data unavailable). "
                "Results are less spatially granular than block-group targeting."
            )

        if len(intents) > 1:
            state_update["structured_data"][0]["combined_demographics_note"] = (
                f"Multi-demographic targeting: combined {' + '.join(intents)} groups. "
                f"Precincts ranked by sum of: {', '.join(combined_primary_metrics or [])}."
            )

        return state_update
