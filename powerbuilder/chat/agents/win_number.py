# powerbuilder/chat/agents/win_number.py
import os
import pandas as pd
from langchain_openai import ChatOpenAI
from ..utils.data_fetcher import DataFetcher
from ..utils.district_standardizer import GeographyStandardizer
from ..utils.census_vars import VOTER_DEMOGRAPHICS
from .state import AgentState

CVAP_KEY = VOTER_DEMOGRAPHICS.get("total_cvap", "B29001_001E")


def get_climate_years(target_year: int) -> tuple:
    """
    Returns (relevant_years: list[int], climate_label: str) for the given election year.
    Exported for use by election_results.py — do not modify without updating that module.

    Classification:
      Presidential  — year divisible by 4 (2016, 2020, 2024)
      Midterm       — even year not divisible by 4 (2014, 2018, 2022)
      Odd-year      — odd year (2017, 2019, 2021, 2023)
    """
    if target_year % 4 == 0:
        return [2016, 2020, 2024], "presidential"
    elif target_year % 2 != 0:
        return [2015, 2017, 2019, 2021, 2023], "odd-year"
    else:
        return [2014, 2018, 2022], "midterm"


class WinNumberAgent:

    @staticmethod
    def calculate_win_math(
        state_fips, district_type, district_id, target_year=2026, victory_margin=0.52
    ):
        """
        Calculates the votes needed to win an election.

        Args:
            state_fips:      2-digit FIPS string, e.g. "51"
            district_type:   "congressional" | "state_senate" | "state_house" | "senate"
            district_id:     GEOID string for House/state races e.g. "5107",
                             or "statewide" for Senate
            target_year:     Election year to project (drives climate matching)
            victory_margin:  Win threshold as a decimal, default 0.52

        Returns a result dict on success, or {"error": str} on failure.
        Climate-matching logic is intentionally preserved unchanged.
        """
        # 1. Fetch Census CVAP for the district
        if district_type == "senate":
            geo_level = "statewide"
        elif district_type in ("congressional", "state_senate", "state_house"):
            geo_level = district_type
        else:
            return {"error": f"Unknown district_type '{district_type}'."}

        census_data = DataFetcher.get_census_data(state_fips, ["total_cvap"], geo_level)

        if not census_data or "error" in census_data[0]:
            return {"error": f"Census CVAP lookup failed for state {state_fips}: "
                             f"{census_data[0].get('error', 'unknown') if census_data else 'no data'}"}

        if district_type == "senate":
            # Statewide: filter for this state by the "state" key
            state_row = next(
                (r for r in census_data if r.get("state") == state_fips), None
            )
            if state_row is None:
                return {"error": f"Statewide CVAP row not found for state {state_fips}."}
            total_cvap = int(float(state_row.get(CVAP_KEY, 0)))
        else:
            # District-level: match on Census geographic key, not NAME (more reliable)
            census_key_map = {
                "congressional": "congressional district",
                "state_senate":  "state legislative district (upper chamber)",
                "state_house":   "state legislative district (lower chamber)",
            }
            census_geo_key = census_key_map[district_type]

            # Extract the district number portion from the GEOID
            # Congressional "5107" → "07"; state_senate "51S007" → "007"
            if district_type == "congressional":
                dist_code = district_id[len(state_fips):]
            else:
                dist_code = district_id[len(state_fips) + 1:]  # strip the S/H prefix

            matched = next(
                (d for d in census_data
                 if "error" not in d and d.get(census_geo_key) == dist_code),
                None
            )
            if matched is None:
                return {
                    "error": (
                        f"District '{district_id}' (code '{dist_code}') not found in Census "
                        f"CVAP data for state {state_fips}. "
                        f"Available districts: "
                        f"{[d.get(census_geo_key) for d in census_data if 'error' not in d]}"
                    )
                }
            total_cvap = int(float(matched.get(CVAP_KEY, 0)))

        # 2. Load historical election data
        path = f"data/election_results/{state_fips}_master.csv"
        try:
            df = pd.read_csv(path)
        except FileNotFoundError:
            return {"error": "Historical data not synced. Run election_ingestor first."}

        # 3. Filter for this district (Senate: statewide, House/state: by GEOID)
        if district_type == "senate":
            history = df[df["district"] == "statewide"]
        else:
            history = df[df["district"] == district_id]

        if history.empty:
            return {
                "error": (
                    f"No historical data found for district '{district_id}' "
                    f"in state {state_fips}. "
                    f"Districts in master CSV: {df['district'].unique().tolist()}"
                )
            }

        # 4. SMART AVERAGE: Match the climate of the target year
        # 2026 is a midterm — weight similar midterm cycles more heavily.
        # Do not change this logic.
        if target_year % 4 == 0:
            relevant_years = [2016, 2020, 2024]  # Presidential climate
        elif target_year % 2 != 0:
            relevant_years = [2015, 2017, 2019, 2021, 2023]  # Odd-year climate
        else:
            relevant_years = [2014, 2018, 2022]  # Midterm climate

        subset = history[history["year"].isin(relevant_years)]
        has_turnout = (
            "turnout_pct" in subset.columns
            and not subset.empty
            and not subset["turnout_pct"].isna().all()
        )
        avg_turnout_pct = subset["turnout_pct"].mean() if has_turnout else 0.50

        # 5. Final math
        projected_turnout = total_cvap * avg_turnout_pct
        win_number = int(projected_turnout * victory_margin)

        return {
            "win_number":         win_number,
            "projected_turnout":  int(projected_turnout),
            "voter_universe_cvap": total_cvap,
            "avg_turnout_pct":    round(avg_turnout_pct, 4),
            "victory_margin":     victory_margin,
            "historical_context": f"Averaged cycles: {relevant_years}",
        }

    @staticmethod
    def run(state: AgentState) -> dict:
        """
        LangGraph node wrapper. Resolves district parameters in priority order:
          1. structured_data — reads context written by a prior agent (e.g. precincts)
          2. LLM extraction from query — fallback when no prior context exists

        Appends result to structured_data, appends "win_number" to active_agents,
        and writes any errors to the errors field.
        """
        # ------------------------------------------------------------------
        # 1. Check structured_data for district context from a prior agent.
        #    Any agent that has already resolved state_fips + district_type +
        #    district_id writes those keys alongside its own results, so we
        #    never re-derive what has already been computed.
        # ------------------------------------------------------------------
        prior = next(
            (
                d for d in state.get("structured_data", [])
                if d.get("state_fips") and d.get("district_type") and d.get("district_id")
            ),
            None,
        )

        if prior:
            state_fips     = prior["state_fips"]
            district_type  = prior["district_type"]
            district_id    = prior["district_id"]
            target_year    = prior.get("target_year", 2026)
            victory_margin = prior.get("victory_margin", 0.52)

        else:
            # ------------------------------------------------------------------
            # 2. Fallback: extract parameters from the query via LLM.
            # ------------------------------------------------------------------
            llm = ChatOpenAI(
                model="gpt-4o",
                temperature=0,
                openai_api_key=os.environ["OPENAI_API_KEY"],
            )

            extraction_prompt = f"""
Extract electoral district information from this query. Return ONLY the five lines below, no extra text.

Query: "{state['query']}"

STATE: [full state name or abbreviation, e.g. "Virginia" or "VA"]
DISTRICT_TYPE: [congressional | state_senate | state_house | senate]
DISTRICT_NUM: [integer district number, or 0 for at-large, or "statewide" for senate]
TARGET_YEAR: [4-digit election year, default 2026]
VICTORY_MARGIN: [decimal win threshold e.g. 0.52, default 0.52]
"""
            try:
                raw = llm.invoke(extraction_prompt).content.strip()
            except Exception as e:
                return {
                    "errors":        [f"WinNumberAgent: LLM extraction failed — {e}"],
                    "active_agents": ["win_number"],
                }

            params = {}
            for line in raw.splitlines():
                if ":" in line:
                    key, _, val = line.partition(":")
                    params[key.strip().upper()] = val.strip().strip('"')

            state_name = params.get("STATE", "")
            state_fips = GeographyStandardizer.STATE_FIPS.get(state_name.lower())
            if not state_fips:
                return {
                    "errors":        [f"WinNumberAgent: Could not resolve state FIPS for '{state_name}'."],
                    "active_agents": ["win_number"],
                }

            district_type = params.get("DISTRICT_TYPE", "congressional").lower()

            try:
                target_year    = int(params.get("TARGET_YEAR", 2026))
                victory_margin = float(params.get("VICTORY_MARGIN", 0.52))
            except ValueError:
                target_year    = 2026
                victory_margin = 0.52

            if district_type == "senate":
                district_id = "statewide"
            else:
                dist_num_raw = params.get("DISTRICT_NUM", "0")
                try:
                    dist_num = int(dist_num_raw)
                except (ValueError, TypeError):
                    return {
                        "errors":        [f"WinNumberAgent: Could not parse district number from '{dist_num_raw}'."],
                        "active_agents": ["win_number"],
                    }
                geoid = GeographyStandardizer.convert_to_geoid(state_name, dist_num, district_type)
                if isinstance(geoid, dict):
                    return {
                        "errors":        [f"WinNumberAgent: {geoid.get('error')}"],
                        "active_agents": ["win_number"],
                    }
                district_id = geoid

        # ------------------------------------------------------------------
        # 3. Run the calculation and write results to state.
        # ------------------------------------------------------------------
        result = WinNumberAgent.calculate_win_math(
            state_fips, district_type, district_id, target_year, victory_margin
        )

        if "error" in result:
            return {
                "errors":        [f"WinNumberAgent: {result['error']}"],
                "active_agents": ["win_number"],
            }

        return {
            "structured_data": [{
                "agent":         "win_number",
                # Carry forward geographic context so further downstream agents
                # (messaging, cost_calculator) can skip their own extraction
                "state_fips":    state_fips,
                "district_type": district_type,
                "district_id":   district_id,
                **result,
            }],
            "active_agents": ["win_number"],
        }
