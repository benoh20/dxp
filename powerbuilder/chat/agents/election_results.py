# powerbuilder/chat/agents/election_results.py
"""
Election Analyst agent. Reads historical election results to surface:
  - Historical margin trend across available cycles (is the district trending
    more or less competitive?)
  - Average D/R vote share broken down by election climate type, using the
    same climate classification as win_number.py (imported, not duplicated)
  - The single most recent election result for context
  - An overall competitiveness classification: Safe, Likely, Lean, or Toss-up

Data sources
------------
Primary  — state master CSVs at data/election_results/{fips}_master.csv
           (written by election_ingestor.py; turnout + cycle metadata)
Secondary — raw MEDSL constituency-returns CSVs (fetched from GitHub, cached
           locally in data/medsl_cache/) for candidate-level D/R vote shares
Cook (optional) — CookPoliticalClient with 24-hour local cache and static seed
           fallback; gracefully absent when COOK_EMAIL/COOK_PASSWORD unset

Output
------
research_results : formatted memo string appended
structured_data  : summary dict appended (agent="election_results")
active_agents    : "election_results" appended
errors           : non-fatal errors appended; agent never raises
"""

import logging
import os
import time
from typing import Optional

import pandas as pd
from langchain_openai import ChatOpenAI

from .state import AgentState
from .win_number import get_climate_years
from ..utils.cook_client import CookPoliticalClient
from ..utils.district_standardizer import GeographyStandardizer
from ..utils.election_ingestor import ElectionDataUtility

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

MASTER_DIR    = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../data/election_results"))
MEDSL_CACHE   = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../data/medsl_cache"))
MEDSL_CACHE_TTL_DAYS = 30  # MEDSL historical data is stable; refresh monthly

# MEDSL raw source URLs (same as election_ingestor.py — imported to avoid duplication)
MEDSL_URLS = ElectionDataUtility.MEDSL_URLS

# Competitiveness thresholds (two-party D margin, e.g. +0.05 = D+5)
# Applied to the average margin across all available cycles.
_COMP_THRESHOLDS = [
    (0.03,  "Toss-up"),
    (0.08,  "Lean"),
    (0.15,  "Likely"),
    (1.00,  "Safe"),
]

# ---------------------------------------------------------------------------
# MEDSL raw data helpers (party-level vote shares)
# ---------------------------------------------------------------------------


def _medsl_cache_path(office_type: str) -> str:
    """Local cache path for the full raw MEDSL CSV (house or senate)."""
    os.makedirs(MEDSL_CACHE, exist_ok=True)
    return os.path.join(MEDSL_CACHE, f"{office_type}_raw.csv")


def _medsl_cache_is_fresh(path: str) -> bool:
    if not os.path.exists(path):
        return False
    age_days = (time.time() - os.path.getmtime(path)) / 86400
    return age_days < MEDSL_CACHE_TTL_DAYS


def _load_medsl_raw(office_type: str) -> Optional[pd.DataFrame]:
    """
    Return the full raw MEDSL CSV for 'house' or 'senate'.
    Uses a local 30-day cache; downloads if absent or stale.
    Returns None on failure.
    """
    if office_type not in ("house", "senate"):
        return None

    cache_path = _medsl_cache_path(office_type)

    if _medsl_cache_is_fresh(cache_path):
        try:
            return pd.read_csv(cache_path, low_memory=False)
        except Exception as e:
            logger.warning(f"ElectionAnalyst: MEDSL cache read error ({office_type}) — {e}")

    url = MEDSL_URLS.get(office_type)
    if not url:
        return None

    try:
        logger.info(f"ElectionAnalyst: downloading MEDSL {office_type} CSV (one-time, cached {MEDSL_CACHE_TTL_DAYS}d)…")
        df = pd.read_csv(url, low_memory=False)
        df.to_csv(cache_path, index=False)
        return df
    except Exception as e:
        logger.warning(f"ElectionAnalyst: MEDSL download failed ({office_type}) — {e}")
        return None


def _extract_party_margins(
    office_type: str,
    state_fips: str,
    district_id: str,
) -> Optional[pd.DataFrame]:
    """
    Return a DataFrame with columns [year, dem_pct, rep_pct, margin, totalvotes]
    for the target district, filtered to general elections.

    'margin' is the two-party D margin: dem_pct - rep_pct  (positive = D advantage).

    Returns None if MEDSL data is unavailable or the district is not found.
    """
    medsl_type = "house" if office_type == "congressional" else "senate"
    raw = _load_medsl_raw(medsl_type)
    if raw is None:
        return None

    fips_int = int(state_fips)

    # Filter to this state + general elections
    df = raw[(raw["state_fips"] == fips_int) & (raw["stage"].str.lower() == "gen")].copy()

    if df.empty:
        return None

    # For congressional: filter by district number extracted from GEOID
    if office_type == "congressional":
        try:
            dist_num = int(district_id[len(state_fips):])
        except (ValueError, IndexError):
            return None
        df = df[df["district"] == dist_num]
    # Senate: all rows in this state are statewide

    if df.empty:
        return None

    # Aggregate votes by year and party
    agg = (
        df.groupby(["year", "party"], as_index=False)["candidatevotes"]
        .sum()
    )
    # Pivot to columns per party
    pivot = agg.pivot(index="year", columns="party", values="candidatevotes").fillna(0)
    pivot.columns.name = None

    # Normalise party column names
    col_map = {}
    for col in pivot.columns:
        c = str(col).lower()
        if "democrat" in c:
            col_map[col] = "dem"
        elif "republican" in c:
            col_map[col] = "rep"
    pivot = pivot.rename(columns=col_map)

    # Total votes per year (sum across all parties)
    total_by_year = df.groupby("year")["totalvotes"].first()
    pivot = pivot.join(total_by_year.rename("totalvotes"))

    if "dem" not in pivot.columns or "rep" not in pivot.columns:
        return None

    pivot["dem_pct"] = pivot["dem"] / pivot["totalvotes"]
    pivot["rep_pct"] = pivot["rep"] / pivot["totalvotes"]
    pivot["margin"]  = pivot["dem_pct"] - pivot["rep_pct"]

    return pivot[["dem_pct", "rep_pct", "margin", "totalvotes"]].reset_index()


# ---------------------------------------------------------------------------
# Competitiveness classification
# ---------------------------------------------------------------------------


def _classify_competitiveness(avg_margin: float) -> str:
    """
    Convert a two-party D margin to a Cook-style competitiveness label.
    avg_margin > 0 = D advantage; < 0 = R advantage.
    """
    party = "D" if avg_margin >= 0 else "R"
    abs_m = abs(avg_margin)
    for threshold, label in _COMP_THRESHOLDS:
        if abs_m <= threshold:
            return "Toss-up" if label == "Toss-up" else f"{label} {party}"
    return f"Safe {party}"


# ---------------------------------------------------------------------------
# Trend analysis
# ---------------------------------------------------------------------------


def _margin_trend(margin_df: pd.DataFrame) -> str:
    """
    Describe the directional trend across cycles.
    Returns a plain-English phrase like "trending more competitive (D margin
    narrowing: +12.3 → +6.8 → +3.1)" or "stable Republican advantage."
    """
    if len(margin_df) < 2:
        return "Insufficient cycles to calculate trend."

    ordered = margin_df.sort_values("year")
    first   = ordered["margin"].iloc[0]
    last    = ordered["margin"].iloc[-1]
    delta   = last - first

    margin_strs = " → ".join(
        f"{'+' if m >= 0 else ''}{m * 100:.1f}%"
        for m in ordered["margin"]
    )

    if abs(delta) < 0.02:
        direction = "stable"
    elif delta > 0:
        direction = "trending more Democratic"
    else:
        direction = "trending more Republican (more competitive)" if last < 0.05 else "trending more Republican"

    return f"{direction} (D margin by cycle: {margin_strs})"


# ---------------------------------------------------------------------------
# Geographic parameter extraction
# ---------------------------------------------------------------------------


def _resolve_params(state: AgentState) -> Optional[dict]:
    """
    Resolve state_fips, district_type, district_id from AgentState.
    Checks structured_data for prior-agent context first, then falls back
    to LLM extraction from the query (same pattern as win_number.py).
    Returns a dict with those keys, or None on failure (caller logs error).
    """
    # 1. Prior agent context on the whiteboard
    prior = next(
        (
            d for d in state.get("structured_data", [])
            if d.get("state_fips") and d.get("district_type") and d.get("district_id")
        ),
        None,
    )
    if prior:
        return {
            "state_fips":    prior["state_fips"],
            "district_type": prior["district_type"],
            "district_id":   prior["district_id"],
            "target_year":   prior.get("target_year", 2026),
        }

    # 2. LLM extraction fallback
    llm = ChatOpenAI(
        model="gpt-4o",
        temperature=0,
        openai_api_key=os.environ["OPENAI_API_KEY"],
    )
    extraction_prompt = f"""
Extract electoral district information from this query. Return ONLY these four lines, no extra text.

Query: "{state['query']}"

STATE: [full state name or abbreviation]
DISTRICT_TYPE: [congressional | state_senate | state_house | senate]
DISTRICT_NUM: [integer district number, or 0 for at-large, or "statewide" for senate]
TARGET_YEAR: [4-digit election year, default 2026]
"""
    try:
        raw = llm.invoke(extraction_prompt).content.strip()
    except Exception as e:
        logger.error(f"ElectionAnalyst: LLM extraction failed — {e}")
        return None

    params = {}
    for line in raw.splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            params[k.strip().upper()] = v.strip().strip('"')

    state_name = params.get("STATE", "")
    state_fips = GeographyStandardizer.STATE_FIPS.get(state_name.lower())
    if not state_fips:
        logger.error(f"ElectionAnalyst: could not resolve FIPS for '{state_name}'")
        return None

    district_type = params.get("DISTRICT_TYPE", "congressional").lower()
    try:
        target_year = int(params.get("TARGET_YEAR", 2026))
    except ValueError:
        target_year = 2026

    if district_type == "senate":
        district_id = "statewide"
    else:
        try:
            dist_num = int(params.get("DISTRICT_NUM", 0))
        except (ValueError, TypeError):
            logger.error("ElectionAnalyst: could not parse district number from LLM output")
            return None
        geoid = GeographyStandardizer.convert_to_geoid(state_name, dist_num, district_type)
        if isinstance(geoid, dict):
            logger.error(f"ElectionAnalyst: GEOID conversion failed — {geoid.get('error')}")
            return None
        district_id = geoid

    return {
        "state_fips":    state_fips,
        "district_type": district_type,
        "district_id":   district_id,
        "target_year":   target_year,
    }


# ---------------------------------------------------------------------------
# Memo builder
# ---------------------------------------------------------------------------


def _build_memo(
    geo: dict,
    district_label: str,
    master_df: Optional[pd.DataFrame],
    margin_df: Optional[pd.DataFrame],
    most_recent: Optional[dict],
    climate_breakdown: Optional[dict],
    trend_note: str,
    competitiveness: str,
    cook: dict,
    errors_list: list,
) -> str:
    target_year = geo["target_year"]
    _, climate_label = get_climate_years(target_year)
    lines = [
        f"--- MEMO FROM SOURCE: Election Analyst | DISTRICT: {district_label}"
        f" | DATE: {most_recent['year'] if most_recent else 'unknown'} ---",
        "",
        f"## Historical Election Analysis — {district_label}",
        "",
    ]

    # Competitiveness
    lines += [
        f"**Overall Competitiveness:** {competitiveness}",
        f"**Trend:** {trend_note}",
        "",
    ]

    # Cook data (if available)
    if cook.get("cook_pvi"):
        lines += [
            "**Cook Political Report:**",
            f"  - Cook PVI: {cook['cook_pvi']}",
        ]
        if cook.get("race_rating"):
            lines.append(f"  - Race Rating: {cook['race_rating']}")
        if cook.get("incumbent"):
            lines.append(f"  - Incumbent: {cook['incumbent']}")
        lines.append(f"  - Source: {cook.get('source', 'seed/cache')}")
        lines.append("")
    else:
        lines += [
            "*Cook Political Report ratings are not currently available for this district. "
            "Enable by setting COOK_EMAIL and COOK_PASSWORD environment variables.*",
            "",
        ]

    # Most recent result
    if most_recent:
        lines += [
            f"**Most Recent Result ({most_recent['year']}):**",
            f"  - Total votes cast: {int(most_recent['totalvotes']):,}",
        ]
        if most_recent.get("dem_pct") is not None:
            lines.append(f"  - Democratic vote share: {most_recent['dem_pct'] * 100:.1f}%")
            lines.append(f"  - Republican vote share: {most_recent['rep_pct'] * 100:.1f}%")
            margin_val = most_recent['margin']
            party_str  = "D" if margin_val >= 0 else "R"
            lines.append(f"  - Two-party margin: {party_str}+{abs(margin_val) * 100:.1f}%")
        lines.append("")

    # Climate breakdown
    if climate_breakdown:
        lines.append(
            f"**Average Vote Share in {climate_label.title()} Cycles "
            f"(target climate for {target_year}):**"
        )
        for climate, row in climate_breakdown.items():
            if row.get("n", 0) > 0:
                m = row["avg_margin"]
                p = "D" if m >= 0 else "R"
                lines.append(
                    f"  - {climate.title()}: D {row['avg_dem_pct'] * 100:.1f}% / "
                    f"R {row['avg_rep_pct'] * 100:.1f}% "
                    f"({p}+{abs(m) * 100:.1f}%, n={row['n']} cycles)"
                )
        lines.append("")

    # Master CSV cycle list (turnout data)
    if master_df is not None and not master_df.empty:
        years_in_csv = sorted(master_df["year"].unique())
        lines += [
            f"**Historical Cycles in Dataset:** {', '.join(str(y) for y in years_in_csv)}",
            "",
        ]

    if errors_list:
        lines += ["**Data Gaps:**"] + [f"  - {e}" for e in errors_list] + [""]

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Node
# ---------------------------------------------------------------------------


def election_results_node(state: AgentState) -> dict:
    """
    Election Analyst LangGraph node. All outputs are appended to whiteboard
    fields; no fields are overwritten. Errors are collected in the errors list
    and never raise.

    Reads from state:
      structured_data, query (fallback for geographic parameter extraction)

    Writes to state:
      research_results, structured_data, active_agents, errors
    """
    errors_out: list = []

    # ------------------------------------------------------------------
    # 1. Resolve geographic parameters
    # ------------------------------------------------------------------
    geo = _resolve_params(state)
    if geo is None:
        return {
            "errors":        ["ElectionAnalyst: could not resolve district parameters from state or query."],
            "active_agents": ["election_results"],
        }

    state_fips    = geo["state_fips"]
    district_type = geo["district_type"]
    district_id   = geo["district_id"]
    target_year   = geo["target_year"]

    # Human-readable district label
    if district_type == "senate":
        fips_to_abbr  = CookPoliticalClient._FIPS_TO_ABBR
        state_abbr    = fips_to_abbr.get(state_fips.zfill(2), state_fips)
        district_label = f"{state_abbr} U.S. Senate"
    else:
        dt_label       = district_type.replace("_", " ").title()
        district_label = (
            f"{dt_label} statewide"
            if district_id == "statewide"
            else f"{dt_label} {district_id}"
        )

    # State legislative races: MEDSL doesn't cover them
    if district_type in ("state_house", "state_senate"):
        errors_out.append(
            f"ElectionAnalyst: MEDSL data covers congressional and U.S. Senate races only. "
            f"State legislative ({district_type}) historical results are not available."
        )

    # ------------------------------------------------------------------
    # 2. Load master CSV (turnout + cycle context)
    # ------------------------------------------------------------------
    master_path = os.path.join(MASTER_DIR, f"{state_fips}_master.csv")
    master_df   = None
    try:
        raw_master = pd.read_csv(master_path)
        if district_id == "statewide":
            master_df = raw_master[raw_master["district"] == "statewide"]
        else:
            master_df = raw_master[raw_master["district"] == district_id]

        if master_df.empty:
            errors_out.append(
                f"ElectionAnalyst: no rows in master CSV for district '{district_id}'. "
                f"Districts available: {raw_master['district'].unique().tolist()}"
            )
            master_df = None
    except FileNotFoundError:
        errors_out.append(
            f"ElectionAnalyst: {master_path} not found. "
            "Run ElectionDataUtility.sync_national_database() first."
        )

    # ------------------------------------------------------------------
    # 3. Load party-level margin data from raw MEDSL
    # ------------------------------------------------------------------
    margin_df = None
    if district_type in ("congressional", "senate"):
        margin_df = _extract_party_margins(district_type, state_fips, district_id)
        if margin_df is None:
            errors_out.append(
                "ElectionAnalyst: MEDSL party-level data unavailable — "
                "margin trend and D/R vote shares cannot be computed. "
                "Turnout data from master CSV will still be used."
            )

    # ------------------------------------------------------------------
    # 4. Compute analytics
    # ------------------------------------------------------------------
    most_recent  = None
    climate_breakdown = None
    trend_note   = "Insufficient data for trend analysis."
    competitiveness = "Unknown"
    avg_margin   = None

    if margin_df is not None and not margin_df.empty:
        # Most recent cycle with party data
        latest    = margin_df.sort_values("year").iloc[-1]
        most_recent = {
            "year":       int(latest["year"]),
            "dem_pct":    round(float(latest["dem_pct"]), 4),
            "rep_pct":    round(float(latest["rep_pct"]), 4),
            "margin":     round(float(latest["margin"]), 4),
            "totalvotes": int(latest["totalvotes"]),
        }

        # Margin trend narrative
        trend_note = _margin_trend(margin_df)

        # Average margin for competitiveness classification
        avg_margin = float(margin_df["margin"].mean())
        competitiveness = _classify_competitiveness(avg_margin)

        # Climate breakdown
        climate_breakdown = {}
        for climate_label_key, years_list in [
            ("presidential", [2016, 2020, 2024]),
            ("midterm",      [2014, 2018, 2022]),
            ("odd-year",     [2015, 2017, 2019, 2021, 2023]),
        ]:
            subset = margin_df[margin_df["year"].isin(years_list)]
            if not subset.empty:
                climate_breakdown[climate_label_key] = {
                    "avg_dem_pct": round(float(subset["dem_pct"].mean()), 4),
                    "avg_rep_pct": round(float(subset["rep_pct"].mean()), 4),
                    "avg_margin":  round(float(subset["margin"].mean()), 4),
                    "n":           len(subset),
                    "cycles":      sorted(subset["year"].tolist()),
                }

    elif master_df is not None and not master_df.empty:
        # Fallback: most recent turnout from master CSV (no party data)
        latest = master_df.sort_values("year").iloc[-1]
        most_recent = {
            "year":       int(latest["year"]),
            "dem_pct":    None,
            "rep_pct":    None,
            "margin":     None,
            "totalvotes": int(latest.get("totalvotes", 0)),
        }

    # ------------------------------------------------------------------
    # 5. Cook Political Report (optional)
    # ------------------------------------------------------------------
    cook_client = CookPoliticalClient()
    cook        = cook_client.fetch(district_type, district_id, state_fips, target_year)

    # Use Cook PVI for competitiveness if margin data wasn't available
    if competitiveness == "Unknown" and cook.get("cook_pvi"):
        pvi = cook["cook_pvi"]
        try:
            party   = "D" if pvi.startswith("D") else "R"
            num_str = pvi.replace("D+", "").replace("R+", "").replace("EVEN", "0")
            num     = float(num_str) / 100.0
            margin  = num if party == "D" else -num
            competitiveness = _classify_competitiveness(margin)
        except (ValueError, AttributeError):
            competitiveness = cook.get("race_rating", "Unknown")

    # ------------------------------------------------------------------
    # 6. Compute climate-matched years for context
    # ------------------------------------------------------------------
    climate_years, climate_name = get_climate_years(target_year)

    # ------------------------------------------------------------------
    # 7. Build memo and structured output
    # ------------------------------------------------------------------
    memo = _build_memo(
        geo             = geo,
        district_label  = district_label,
        master_df       = master_df,
        margin_df       = margin_df,
        most_recent     = most_recent,
        climate_breakdown = climate_breakdown,
        trend_note      = trend_note,
        competitiveness = competitiveness,
        cook            = cook,
        errors_list     = errors_out,
    )

    structured = {
        "agent":            "election_results",
        "state_fips":       state_fips,
        "district_type":    district_type,
        "district_id":      district_id,
        "target_year":      target_year,
        "competitiveness":  competitiveness,
        "trend":            trend_note,
        "avg_margin":       round(avg_margin, 4) if avg_margin is not None else None,
        "most_recent":      most_recent,
        "climate_breakdown": climate_breakdown,
        "cook_pvi":         cook.get("cook_pvi"),
        "race_rating":      cook.get("race_rating"),
        "incumbent":        cook.get("incumbent"),
        "cook_source":      cook.get("source"),
    }

    logger.info(
        f"ElectionAnalyst: {district_label} — {competitiveness} | "
        f"trend: {trend_note[:60]}…"
    )

    result = {
        "research_results": [memo],
        "structured_data":  [structured],
        "active_agents":    ["election_results"],
    }
    if errors_out:
        result["errors"] = errors_out
    return result


# ---------------------------------------------------------------------------
# Class wrapper (matches WinNumberAgent / PrecinctsAgent API)
# ---------------------------------------------------------------------------

class ElectionAnalystAgent:
    """Thin class wrapper so manager.py can import consistently."""

    @staticmethod
    def run(state: AgentState) -> dict:
        return election_results_node(state)
