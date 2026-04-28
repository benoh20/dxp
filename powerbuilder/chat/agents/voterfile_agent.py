# powerbuilder/chat/agents/voterfile_agent.py
#
# PROTOTYPE NOTICE — SYNTHETIC / FAKE DATA ONLY
# This module is built for demonstration purposes using synthetic data.
#
# BEFORE PRODUCTION USE, the following must be addressed:
#   - Encrypted storage at rest and in transit for all voter PII
#   - Strict org-level data isolation (no cross-org data leakage)
#   - Defined data retention and automatic deletion policies
#   - Compliance review under applicable voter data laws (CCPA, state election codes)
#   - Role-based access controls limiting who can upload and view voter files
#   - Audit logging of all access to voter file data
#   - Field standardization validated against each vendor's current schema version
#
# Raw voter data is NOT persisted beyond the active request session.
# The file is read from the temporary upload path and discarded after analysis.
# gc.collect() is called after analysis to release memory promptly.

import gc
import logging
import os

import pandas as pd

from .researcher import research_node
from .state import AgentState

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Step 1 — Field standardization schema
# Maps standard internal field name → list of vendor-specific aliases (case-insensitive).
# First alias that matches the DataFrame columns wins.
# ---------------------------------------------------------------------------

FIELD_SCHEMA: dict[str, list[str]] = {
    # Identifiers
    "voter_id":              ["voter_id", "vanid", "van_id", "tsmart_key", "voterbase_id",
                              "catalist_id", "l2_id", "state_voter_id", "registrant_id", "id"],
    "first_name":            ["first_name", "firstname", "fname", "LFirstName", "first",
                              "tsmart_first_name", "voterbase_first_name"],
    "last_name":             ["last_name", "lastname", "lname", "LLastName", "last",
                              "tsmart_last_name", "voterbase_last_name"],
    "full_name":             ["full_name", "fullname", "name", "tsmart_full_name"],

    # Geography
    "address":               ["address", "street_address", "mailing_address", "residence_address"],
    "city":                  ["city", "res_city", "mailing_city"],
    "state":                 ["state", "res_state", "state_code"],
    "zip":                   ["zip", "zipcode", "zip_code", "postal_code"],
    "county":                ["county", "county_name", "res_county"],
    "precinct":              ["precinct", "precinct_name", "precinct_code", "ward"],
    "congressional_district":["congressional_district", "cd", "us_cong_dist", "cong_dist"],
    "state_senate_district": ["state_senate_district", "state_senate", "sd", "senate_district"],
    "state_house_district":  ["state_house_district", "state_house", "hd", "house_district"],

    # Demographics
    "age":                   ["age", "voter_age", "Age", "voterbase_age", "tsmart_age"],
    "dob":                   ["dob", "date_of_birth", "birth_date", "birthdate",
                              "voterbase_dob", "tsmart_dob"],
    "gender":                ["gender", "sex", "gender_code", "LGender",
                              "voterbase_gender", "tsmart_gender"],
    "race":                  ["race", "race_ethnicity", "ethnicity", "race_ethnic",
                              "LRace", "tsmart_race", "cat_race"],
    "party_registration":    ["party_registration", "party", "party_code", "registration_party",
                              "LParty", "party_affiliation"],

    # Scores
    "partisan_score":        ["partisan_score", "tsmart_partisan_score", "dem_score",
                              "partisanship_score", "LikelyDem", "partisan", "dem_support_score"],
    "turnout_score":         ["turnout_score", "tsmart_vote_propensity", "vote_propensity_score",
                              "vote_propensity", "turnout_propensity", "LGeneralVoteScore",
                              "general_score"],
    "spanish_speaking_score":["spanish_speaking_score", "tsmart_spanish_language_score",
                              "spanish_score", "hispanic_language_score"],

    # Registration
    "registration_date":     ["registration_date", "reg_date", "date_registered",
                              "voter_registration_date", "registered_date"],

    # Vote history
    "vote_history_2024":     ["vote_history_2024", "g2024", "general_2024", "voted_2024",
                              "LGeneralVoting2024"],
    "vote_history_2022":     ["vote_history_2022", "g2022", "general_2022", "voted_2022",
                              "LGeneralVoting2022"],
    "vote_history_2020":     ["vote_history_2020", "g2020", "general_2020", "voted_2020",
                              "LGeneralVoting2020"],
    "vote_history_2018":     ["vote_history_2018", "g2018", "general_2018", "voted_2018",
                              "LGeneralVoting2018"],
}

# ---------------------------------------------------------------------------
# Step 2 — Vendor detection hints
# Unique fields that fingerprint a specific vendor's export format.
# ---------------------------------------------------------------------------

VENDOR_HINTS: dict[str, list[str]] = {
    "TargetSmart": ["tsmart_partisan_score", "tsmart_key", "tsmart_vote_propensity",
                    "tsmart_race", "tsmart_spanish_language_score"],
    "Catalist":    ["dem_score", "catalist_id", "cat_race"],
    "L2":          ["LikelyDem", "LFirstName", "LLastName", "LGender", "LParty",
                    "LGeneralVoteScore", "LRace"],
    "VAN":         ["vanid", "van_id"],
}

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VOTE_HISTORY_COLS = ["vote_history_2020", "vote_history_2022", "vote_history_2024",
                     "vote_history_2018"]

_MAX_MESSAGING_QUERIES = 6


# ---------------------------------------------------------------------------
# Step 3 — Column standardization
# ---------------------------------------------------------------------------

def standardize_columns(df: pd.DataFrame) -> tuple[pd.DataFrame, str, dict]:
    """
    Rename vendor-specific columns to standard internal names.

    Returns:
        df              : DataFrame with standardized column names
        vendor          : Detected vendor name or "Unknown"
        field_availability: {standard_name: True/False} for all FIELD_SCHEMA keys
    """
    df = df.copy()

    # Normalize raw column names to lowercase_underscore for alias matching
    raw_cols_lower = {c.lower().strip().replace(" ", "_"): c for c in df.columns}

    rename_map: dict[str, str] = {}
    for standard_name, aliases in FIELD_SCHEMA.items():
        if standard_name in df.columns:
            continue  # already correct
        for alias in aliases:
            alias_lower = alias.lower().strip().replace(" ", "_")
            if alias_lower in raw_cols_lower:
                original = raw_cols_lower[alias_lower]
                if original != standard_name:
                    rename_map[original] = standard_name
                break

    df = df.rename(columns=rename_map)

    # Detect vendor from original column names (before rename)
    original_cols_lower = set(raw_cols_lower.keys())
    vendor = "Unknown"
    for vendor_name, hints in VENDOR_HINTS.items():
        if any(h.lower().replace(" ", "_") in original_cols_lower for h in hints):
            vendor = vendor_name
            break

    # Build field availability map
    field_availability = {name: (name in df.columns) for name in FIELD_SCHEMA}

    return df, vendor, field_availability


# ---------------------------------------------------------------------------
# Step 4 — Column coercion
# ---------------------------------------------------------------------------

def _coerce_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Coerce typed columns to correct dtypes after standardization."""
    df = df.copy()

    # Vote history → bool
    for col in VOTE_HISTORY_COLS:
        if col in df.columns:
            df[col] = (
                df[col].astype(str).str.strip().str.upper()
                .isin(["TRUE", "1", "YES", "Y"])
            )

    # Numeric scores
    for col in ["partisan_score", "turnout_score", "spanish_speaking_score"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Age
    if "age" in df.columns:
        df["age"] = pd.to_numeric(df["age"], errors="coerce")

    # Registration date
    if "registration_date" in df.columns:
        df["registration_date"] = pd.to_datetime(df["registration_date"], errors="coerce")

    return df


# ---------------------------------------------------------------------------
# Step 5 — Derived segmentation columns
# ---------------------------------------------------------------------------

def _age_cohort(age) -> str:
    try:
        age = int(age)
    except (ValueError, TypeError):
        return "Unknown"
    if 18 <= age <= 26:
        return "Gen Z (18-26)"
    if 27 <= age <= 42:
        return "Millennial (27-42)"
    if 43 <= age <= 58:
        return "Gen X (43-58)"
    if 59 <= age <= 77:
        return "Boomer (59-77)"
    if age >= 78:
        return "Silent/Greatest (78+)"
    return "Unknown"


def _partisan_tier(score) -> str:
    try:
        s = float(score)
    except (ValueError, TypeError):
        return "New/Unscored"
    if s >= 70:
        return "Strong Dem (70-100)"
    if s >= 55:
        return "Persuadable Dem (55-69)"
    if s >= 35:
        return "True Persuadable (35-54)"
    if s >= 31:
        return "Persuadable Rep (31-34)"
    return "Strong Rep (0-30)"


def _turnout_tier(score) -> str:
    try:
        s = float(score)
    except (ValueError, TypeError):
        return "Unscored"
    if s >= 80:
        return "High (80-100)"
    if s >= 60:
        return "Med-High (60-79)"
    if s >= 20:
        return "Med-Low (20-59)"
    return "Low (0-19)"


def _vote_history_class(row: pd.Series) -> str:
    present = [c for c in VOTE_HISTORY_COLS if c in row.index]
    if not present:
        return "Unknown"
    voted = sum(1 for c in present if row[c])
    total = len(present)
    if voted >= 3:
        return f"Consistent High ({voted}/{total} cycles)"
    if voted >= 1:
        return f"Occasional ({voted}/{total} cycles)"
    return f"Non-Voter (0/{total} cycles)"


def _normalize_gender(val) -> str:
    v = str(val).strip().upper()
    if v in ("F", "FEMALE", "WOMAN", "W"):
        return "Female"
    if v in ("M", "MALE", "MAN"):
        return "Male"
    if v in ("NAN", "NONE", "", "UNKNOWN", "U"):
        return "Unknown"
    return "Gender Expansive"


def _normalize_race(val) -> str:
    v = str(val).strip().upper()
    if any(k in v for k in ("BLACK", "AFRICAN")):
        return "Black/African American"
    if any(k in v for k in ("HISPANIC", "LATINO", "LATINA", "LATINX")):
        return "Hispanic/Latino"
    if any(k in v for k in ("ASIAN", "AAPI", "PACIFIC")):
        return "Asian/AAPI"
    if any(k in v for k in ("NATIVE", "INDIGENOUS", "INDIAN", "ALASKA")):
        return "Native American/Indigenous"
    if any(k in v for k in ("WHITE", "CAUCASIAN")):
        return "White"
    if v in ("NAN", "NONE", "", "UNKNOWN", "U"):
        return "Unknown"
    return "Other"


def _is_new_registrant(row: pd.Series, cutoff_date) -> bool:
    """New if registered within 18 months OR both partisan+turnout scores are null."""
    both_null = (
        pd.isna(row.get("partisan_score")) and pd.isna(row.get("turnout_score"))
    )
    if both_null:
        return True
    reg = row.get("registration_date")
    if pd.notna(reg) and cutoff_date is not None:
        return reg >= cutoff_date
    return False


def _add_derived_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    if "age" in df.columns:
        df["_age_cohort"] = df["age"].apply(_age_cohort)

    if "partisan_score" in df.columns:
        df["_partisan_tier"] = df["partisan_score"].apply(_partisan_tier)
    else:
        df["_partisan_tier"] = "New/Unscored"

    if "turnout_score" in df.columns:
        df["_turnout_tier"] = df["turnout_score"].apply(_turnout_tier)
    else:
        df["_turnout_tier"] = "Unscored"

    history_present = [c for c in VOTE_HISTORY_COLS if c in df.columns]
    if history_present:
        df["_vote_history_class"] = df.apply(_vote_history_class, axis=1)

    if "gender" in df.columns:
        df["_gender_norm"] = df["gender"].apply(_normalize_gender)

    if "race" in df.columns:
        df["_race_norm"] = df["race"].apply(_normalize_race)

    # New registrant flag — 18-month lookback from today
    try:
        from datetime import date, timedelta
        cutoff = pd.Timestamp(date.today() - timedelta(days=548))
    except Exception:
        cutoff = None

    if "registration_date" in df.columns or "partisan_score" in df.columns or "turnout_score" in df.columns:
        df["_new_registrant"] = df.apply(
            lambda r: _is_new_registrant(r, cutoff), axis=1
        )

    return df


# ---------------------------------------------------------------------------
# Step 6 — Segment table
# ---------------------------------------------------------------------------

_SEGMENT_DIMENSIONS = [
    ("Age Cohort",         "_age_cohort"),
    ("Partisan Tier",      "_partisan_tier"),
    ("Turnout Tier",       "_turnout_tier"),
    ("Party",              "party_registration"),
    ("Gender",             "_gender_norm"),
    ("Race/Ethnicity",     "_race_norm"),
    ("Vote History Class", "_vote_history_class"),
]

_SCORE_COLS = ["partisan_score", "turnout_score", "spanish_speaking_score"]


def _build_segment_table(df: pd.DataFrame) -> list[dict]:
    total = len(df)
    segments: list[dict] = []

    for dim_label, col in _SEGMENT_DIMENSIONS:
        if col not in df.columns:
            continue
        for value, group in df.groupby(col, dropna=False):
            value_str = str(value) if pd.notna(value) else "Unknown"
            seg: dict = {
                "dimension":   dim_label,
                "segment":     value_str,
                "description": f"{value_str} ({dim_label.lower()})",
                "count":       len(group),
                "pct_of_file": round(len(group) / total * 100, 1),
            }
            for score_col in _SCORE_COLS:
                if score_col in group.columns and group[score_col].notna().any():
                    seg[f"avg_{score_col}"] = round(float(group[score_col].mean()), 2)

            if "_gender_norm" in group.columns and col != "_gender_norm":
                seg["gender_breakdown"] = group["_gender_norm"].value_counts().to_dict()
            if "party_registration" in group.columns and col != "party_registration":
                seg["party_breakdown"] = group["party_registration"].value_counts().to_dict()

            segments.append(seg)

    # Step 6b — Cross-tab priority matrix: High Value, Secondary, New Registrants
    if "_partisan_tier" in df.columns and "_turnout_tier" in df.columns:
        high_value_mask = (
            df["_partisan_tier"].isin(["Strong Dem (70-100)", "Persuadable Dem (55-69)"])
            & df["_turnout_tier"].isin(["High (80-100)", "Med-High (60-79)"])
        )
        hv_count = int(high_value_mask.sum())
        if hv_count > 0:
            hv_group = df[high_value_mask]
            hv_seg: dict = {
                "dimension":   "Priority Cross-Tab",
                "segment":     "High Value (Dem 55-100 + Turnout 60-100)",
                "description": "High Value (Dem 55-100 + Turnout 60-100) (priority cross-tab)",
                "count":       hv_count,
                "pct_of_file": round(hv_count / total * 100, 1),
                "priority":    "HIGH",
            }
            for score_col in _SCORE_COLS:
                if score_col in hv_group.columns and hv_group[score_col].notna().any():
                    hv_seg[f"avg_{score_col}"] = round(float(hv_group[score_col].mean()), 2)
            segments.append(hv_seg)

        sec_mask = (
            df["_partisan_tier"].isin([
                "True Persuadable (35-54)", "Persuadable Dem (55-69)",
                "Persuadable Rep (31-34)"
            ])
        )
        sec_count = int(sec_mask.sum())
        if sec_count > 0:
            segments.append({
                "dimension":   "Priority Cross-Tab",
                "segment":     "Secondary (Persuadable, any turnout)",
                "description": "Secondary (Persuadable, any turnout) (priority cross-tab)",
                "count":       sec_count,
                "pct_of_file": round(sec_count / total * 100, 1),
                "priority":    "SECONDARY",
            })

    if "_new_registrant" in df.columns:
        nr_count = int(df["_new_registrant"].sum())
        if nr_count > 0:
            segments.append({
                "dimension":   "Priority Cross-Tab",
                "segment":     "New Registrants",
                "description": "New Registrants (priority cross-tab)",
                "count":       nr_count,
                "pct_of_file": round(nr_count / total * 100, 1),
                "priority":    "NEW_REGISTRANT",
            })

    return segments


# ---------------------------------------------------------------------------
# Pinecone messaging fetch
# ---------------------------------------------------------------------------

def _fetch_messaging(segment_description: str, state: AgentState) -> str:
    query = f"messaging strategy and voter contact approach for {segment_description} voters"
    proxy_state = {**state, "query": query}
    try:
        result = research_node(proxy_state)
        findings = result.get("research_results", [])
        return "\n\n".join(findings[:2]) if findings else "No matching research found."
    except Exception as e:
        logger.warning(f"VoterFileAgent: Pinecone query failed for '{segment_description}': {e}")
        return "Research query failed — check Pinecone connection."


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

class VoterFileAgent:
    """
    Voter File Analyst — standardizes vendor-specific field names, segments
    voters by demographic and turnout attributes, applies a cross-tab priority
    matrix, then pulls messaging research from Pinecone for top segments.

    Input  (from AgentState):  uploaded_file_path (CSV or Excel)
    Output (to AgentState):
        structured_data  — segment breakdown table + file summary + vendor info
        research_results — per-segment messaging memos
        active_agents    — ["voter_file"]
    """

    @staticmethod
    def run(state: AgentState) -> dict:
        file_path = state.get("uploaded_file_path", "")

        if not file_path or not os.path.exists(file_path):
            return {
                "errors":        ["VoterFileAgent: No voter file in session. "
                                  "Upload a CSV or Excel file to analyse."],
                "active_agents": ["voter_file"],
            }

        try:
            ext = os.path.splitext(file_path)[1].lower()
            if ext in (".xlsx", ".xls"):
                df = pd.read_excel(file_path)
            else:
                df = pd.read_csv(file_path, low_memory=False)
        except Exception as e:
            return {
                "errors":        [f"VoterFileAgent: Could not read file — {e}"],
                "active_agents": ["voter_file"],
            }

        if df.empty:
            return {
                "errors":        ["VoterFileAgent: Uploaded file contains no rows."],
                "active_agents": ["voter_file"],
            }

        # Standardize → coerce → derive
        df, vendor, field_availability = standardize_columns(df)
        df = _coerce_columns(df)
        df = _add_derived_columns(df)
        total_voters = len(df)

        # Build segment table (includes cross-tab priority rows)
        segments = _build_segment_table(df)

        # File-level summary
        summary: dict = {
            "total_voters":        total_voters,
            "vendor_detected":     vendor,
            "fields_available":    [k for k, v in field_availability.items() if v],
            "fields_missing":      [k for k, v in field_availability.items() if not v],
            "segments_identified": len(segments),
        }

        for col, label in [
            ("party_registration",  "party_breakdown"),
            ("_age_cohort",         "age_cohort_breakdown"),
            ("_partisan_tier",      "partisan_tier_breakdown"),
            ("_turnout_tier",       "turnout_tier_breakdown"),
            ("_gender_norm",        "gender_breakdown"),
            ("_race_norm",          "race_breakdown"),
            ("_vote_history_class", "vote_history_breakdown"),
        ]:
            if col in df.columns:
                summary[label] = df[col].value_counts().to_dict()

        for score_col, label in [
            ("partisan_score",        "avg_partisan_score"),
            ("turnout_score",         "avg_turnout_score"),
            ("spanish_speaking_score","avg_spanish_speaking_score"),
        ]:
            if score_col in df.columns and df[score_col].notna().any():
                summary[label] = round(float(df[score_col].mean()), 2)

        if "_new_registrant" in df.columns:
            summary["new_registrants"] = int(df["_new_registrant"].sum())

        # Release DataFrame memory before Pinecone queries
        del df
        gc.collect()

        # Query Pinecone for top segments (>5% of file, max 6)
        top_segments = sorted(
            [s for s in segments if s["pct_of_file"] >= 5.0],
            key=lambda s: s["count"],
            reverse=True,
        )
        # Always include priority cross-tab segments regardless of % threshold
        priority_segs = [s for s in segments if s.get("priority") and s["count"] >= 5]
        for ps in priority_segs:
            if ps not in top_segments:
                top_segments.insert(0, ps)

        messaging_memos: list[str] = []
        for seg in top_segments[:_MAX_MESSAGING_QUERIES]:
            if seg["count"] < 5:
                continue
            research = _fetch_messaging(seg["description"], state)
            priority_badge = f" [{seg['priority']}]" if seg.get("priority") else ""
            header = (
                f"## Messaging Guidance — {seg['description']}{priority_badge}\n"
                f"**Voters in segment:** {seg['count']:,} ({seg['pct_of_file']}% of file)\n"
            )
            if "avg_partisan_score" in seg:
                header += f"**Avg partisan score:** {seg['avg_partisan_score']}\n"
            if "avg_turnout_score" in seg:
                header += f"**Avg turnout score:** {seg['avg_turnout_score']}\n"
            messaging_memos.append(header + "\n" + research)

        return {
            "structured_data": [{
                "agent":            "voter_file",
                "vendor_detected":  vendor,
                "summary":          summary,
                "segments":         segments,
            }],
            "research_results": messaging_memos,
            "active_agents":    ["voter_file"],
            "errors": (
                ["VoterFileAgent: No matching Pinecone research found for any segment — "
                 "verify that the research library is populated."]
                if not messaging_memos else []
            ),
        }
