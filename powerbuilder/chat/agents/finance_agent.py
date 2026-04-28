# powerbuilder/chat/agents/finance_agent.py
"""
Accountant agent. Estimates campaign program costs in two complementary modes:

1. HISTORICAL MODE (federal races only): Fetches FEC disbursement totals for
   comparable candidates in similar election cycles (e.g. prior midterms for a
   2026 race), then applies industry-standard spending distribution percentages to
   derive a category breakdown. Falls back to statewide averages if district-specific
   data is sparse, and to unit-cost-only mode if FEC is unreachable.

2. UNIT COST MODE: Always produced alongside (or instead of) historical data.
   Given a user-supplied budget — or contact goals derived from the win number —
   calculates how many doors, calls, texts, and mail pieces that budget can fund
   using per-contact rate defaults. Rates can be overridden by dropping a
   unit_costs.json file into powerbuilder/tool_templates/.

State legislative races (state_senate, state_house) have no FEC coverage and run
in unit-cost-only mode by default.

Outputs written to AgentState:
  structured_data:  one budget breakdown dict (appended)
  research_results: one narrative budget memo (appended)
  active_agents:    ["finance"]
  errors:           FEC API failures (non-fatal — unit cost mode continues)
"""

import json
import logging
import os
import re
from typing import Optional

from dotenv import load_dotenv
load_dotenv()

from langchain_openai import ChatOpenAI

from ..utils.data_fetcher import DataFetcher
from ..utils.district_standardizer import GeographyStandardizer
from .state import AgentState
from .paid_media import (
    estimate_paid_media,
    format_paid_media_section,
    query_mentions_paid_media,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

TEMPLATES_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "../../tool_templates")
)

# Fallback rates used when costs.json is absent or a key is missing.
# Primary source is tool_templates/costs.json — edit that file to change rates.
DEFAULT_UNIT_COSTS = {
    "door_knock":      7.00,   # canvasser labor + lit + overhead per door
    "doors_per_hour":  8,      # average doors contacted per canvasser hour
    "phone_call":      1.50,   # dialer service + volunteer coordination per call
    "text_message":    0.05,   # peer-to-peer platform per outgoing text
    "mail_piece":      1.00,   # print + postage per piece
    "mail_design_fee": 500,    # flat design fee per mail program
    "digital_cpm":     0.02,   # cost per impression
    "digital_minimum": 1000,   # minimum spend per platform per flight
}

# How total disbursements are typically distributed across categories,
# by race type. Derived from FEC itemized disbursement research.
SPENDING_DISTRIBUTION = {
    "congressional": {
        "personnel":     0.35,
        "mail":          0.20,
        "digital":       0.25,
        "phones":        0.10,
        "miscellaneous": 0.10,
    },
    "senate": {
        "personnel":     0.40,
        "mail":          0.15,
        "digital":       0.30,
        "phones":        0.05,
        "miscellaneous": 0.10,
    },
    # State legislative races have no FEC data — these distributions are used
    # only when the synthesizer builds a narrative from unit cost projections.
    "state_senate": {
        "personnel":     0.30,
        "mail":          0.30,
        "digital":       0.15,
        "phones":        0.15,
        "miscellaneous": 0.10,
    },
    "state_house": {
        "personnel":     0.25,
        "mail":          0.35,
        "digital":       0.10,
        "phones":        0.20,
        "miscellaneous": 0.10,
    },
}

# FEC election cycles to average for comparable-climate projection.
# Keys are the target election year; values are prior cycles of the same type.
COMPARABLE_CYCLES = {
    "midterm":     [2022, 2018],
    "presidential": [2020, 2016],
    "odd":         [2021, 2017],
}

# Map district_type → FEC office code. State legislative types have no FEC data.
FEC_OFFICE_MAP = {
    "congressional": "H",
    "senate":        "S",
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Build FIPS → 2-char state abbreviation from the standardizer's lookup table.
# STATE_FIPS maps both full-name and abbreviation keys to the same FIPS value;
# keeping only 2-char keys gives us the abbreviation for each state.
_FIPS_TO_ABBR: dict = {
    fips: abbr.upper()
    for abbr, fips in GeographyStandardizer.STATE_FIPS.items()
    if len(abbr) == 2
}


def _load_unit_costs() -> dict:
    """
    Load per-contact rates from tool_templates/costs.json, mapping the nested
    JSON structure to the flat dict used internally. Falls back to DEFAULT_UNIT_COSTS
    key-by-key so partial files are safe.
    """
    path = os.path.join(TEMPLATES_DIR, "costs.json")
    try:
        with open(path) as f:
            raw = json.load(f)
        costs = {
            "door_knock":      raw.get("canvassing", {}).get("cost_per_door",      DEFAULT_UNIT_COSTS["door_knock"]),
            "doors_per_hour":  raw.get("canvassing", {}).get("doors_per_hour",     DEFAULT_UNIT_COSTS["doors_per_hour"]),
            "phone_call":      raw.get("phones",     {}).get("cost_per_contact",   DEFAULT_UNIT_COSTS["phone_call"]),
            "text_message":    raw.get("text",       {}).get("cost_per_text",      DEFAULT_UNIT_COSTS["text_message"]),
            "mail_piece":      raw.get("mail",       {}).get("cost_per_piece",     DEFAULT_UNIT_COSTS["mail_piece"]),
            "mail_design_fee": raw.get("mail",       {}).get("design_fee_flat",    DEFAULT_UNIT_COSTS["mail_design_fee"]),
            "digital_cpm":     raw.get("digital",    {}).get("cost_per_impression",DEFAULT_UNIT_COSTS["digital_cpm"]),
            "digital_minimum": raw.get("digital",    {}).get("minimum_spend",      DEFAULT_UNIT_COSTS["digital_minimum"]),
        }
        logger.debug(f"Loaded unit costs from costs.json")
        return costs
    except FileNotFoundError:
        logger.debug("costs.json not found; using DEFAULT_UNIT_COSTS.")
        return DEFAULT_UNIT_COSTS
    except Exception as e:
        logger.warning(f"Could not parse costs.json — {e}. Using defaults.")
        return DEFAULT_UNIT_COSTS


def _parse_dollar(formatted: str) -> float:
    """
    Parse a dollar-formatted string back to float.
    e.g. '$1,234,567.89' → 1234567.89
    Returns 0.0 on failure so downstream math never crashes.
    """
    try:
        return float(re.sub(r"[^\d.]", "", str(formatted)))
    except (ValueError, TypeError):
        return 0.0


def _pick_cycles(target_year: int) -> list:
    """
    Select comparable historical FEC cycles based on the climate of target_year.
    """
    if target_year % 4 == 0:
        return COMPARABLE_CYCLES["presidential"]
    elif target_year % 2 != 0:
        return COMPARABLE_CYCLES["odd"]
    else:
        return COMPARABLE_CYCLES["midterm"]


def _fetch_fec_average(
    state_abbr: str,
    district_num: str,
    office: str,
    cycles: list,
) -> dict:
    """
    Fetch FEC disbursement totals for the given race across all comparable cycles
    and return the average disbursement figure alongside metadata.

    Returns:
        {
            "avg_disbursements": float,
            "candidates_sampled": int,
            "cycles_found": list,
            "error": str | None,
        }
    Falls back to statewide average when district-level data is empty.
    """
    all_disbursements = []
    cycles_found = []
    errors = []

    # Parse the district number out of the GEOID for FEC calls.
    # congressional "5107" → "07"; senate is always "00"
    if office == "S":
        dist_param = "00"
    else:
        # district_num is passed in already stripped (just the numeric suffix)
        dist_param = district_num

    for cycle in cycles:
        try:
            results = DataFetcher.get_district_finances(
                state=state_abbr,
                district_number=dist_param,
                office_type=office,
                cycle=cycle,
            )
            if isinstance(results, dict) and "error" in results:
                errors.append(f"Cycle {cycle}: {results['error']}")
                continue
            if not results:
                continue

            for candidate in results:
                val = _parse_dollar(candidate.get("total_disbursements", "0"))
                if val > 0:
                    all_disbursements.append(val)
                    if cycle not in cycles_found:
                        cycles_found.append(cycle)
        except Exception as e:
            errors.append(f"Cycle {cycle}: {e}")

    # If district-level pull returned nothing, try statewide as a fallback.
    if not all_disbursements and office == "H":
        logger.warning(
            f"No district-level FEC data for {state_abbr}-{dist_param}; "
            "trying statewide House average."
        )
        for cycle in cycles:
            try:
                results = DataFetcher.get_district_finances(
                    state=state_abbr,
                    district_number="00",
                    office_type=office,
                    cycle=cycle,
                )
                if isinstance(results, list):
                    for candidate in results:
                        val = _parse_dollar(candidate.get("total_disbursements", "0"))
                        if val > 0:
                            all_disbursements.append(val)
                            if cycle not in cycles_found:
                                cycles_found.append(cycle)
            except Exception:
                pass

    if not all_disbursements:
        return {
            "avg_disbursements": 0.0,
            "candidates_sampled": 0,
            "cycles_found": [],
            "error": "; ".join(errors) if errors else "No FEC data found.",
        }

    return {
        "avg_disbursements": sum(all_disbursements) / len(all_disbursements),
        "candidates_sampled": len(all_disbursements),
        "cycles_found": sorted(cycles_found),
        "error": None,
    }


def _build_category_breakdown(total: float, district_type: str) -> dict:
    """
    Apply the spending distribution for this race type to a total disbursement
    figure and return a dict of category → dollar amount.
    """
    dist = SPENDING_DISTRIBUTION.get(district_type, SPENDING_DISTRIBUTION["congressional"])
    return {cat: round(total * pct, 2) for cat, pct in dist.items()}


def _build_budget_program(budget: float, unit_costs: dict) -> dict:
    """
    Given a total budget, allocate across tactics using recommended splits.
    Digital is only included when the budget is large enough to clear the
    minimum spend threshold meaningfully. Mail allocation accounts for the
    flat design fee before calculating piece count.

    Default splits (with digital): canvassing 35%, phones 20%, texts 10%, mail 25%, digital 10%
    Default splits (without digital): canvassing 40%, phones 20%, texts 15%, mail 25%
    """
    design_fee    = unit_costs.get("mail_design_fee", DEFAULT_UNIT_COSTS["mail_design_fee"])
    digital_min   = unit_costs.get("digital_minimum", DEFAULT_UNIT_COSTS["digital_minimum"])

    # Only include digital if budget covers the minimum plus meaningful scale
    use_digital = budget >= digital_min * 3

    if use_digital:
        splits = {"door_knock": 0.35, "phone_call": 0.20,
                  "text_message": 0.10, "mail_piece": 0.25, "digital": 0.10}
    else:
        splits = {"door_knock": 0.40, "phone_call": 0.20,
                  "text_message": 0.15, "mail_piece": 0.25}

    rate_keys = {
        "door_knock":   "door_knock",
        "phone_call":   "phone_call",
        "text_message": "text_message",
        "mail_piece":   "mail_piece",
        "digital":      "digital_cpm",
    }

    program = {}
    for tactic, pct in splits.items():
        allocated = budget * pct
        rate      = unit_costs.get(rate_keys[tactic], DEFAULT_UNIT_COSTS.get(rate_keys[tactic], 1.0))

        if tactic == "mail_piece":
            net_for_pieces = max(0.0, allocated - design_fee)
            contacts = int(net_for_pieces / rate) if rate > 0 else 0
            program[tactic] = {
                "budget_allocated": round(allocated, 2),
                "unit_cost":        rate,
                "design_fee":       design_fee,
                "contacts":         contacts,
                "note":             f"Includes ${design_fee:,.0f} flat design fee",
            }
        elif tactic == "digital":
            impressions = int(allocated / rate) if rate > 0 else 0
            program[tactic] = {
                "budget_allocated": round(allocated, 2),
                "unit_cost":        rate,
                "contacts":         impressions,
                "note":             "Impressions (not unique contacts)",
            }
        else:
            contacts = int(allocated / rate) if rate > 0 else 0
            program[tactic] = {
                "budget_allocated": round(allocated, 2),
                "unit_cost":        rate,
                "contacts":         contacts,
            }
    return program


def _build_voter_file_budget(universe_size: int, unit_costs: dict) -> dict:
    """
    Cost to contact the full voter file universe once per tactic.
    Returns tactic → {contacts, unit_cost, total_cost, note?}.
    """
    design_fee  = unit_costs.get("mail_design_fee", DEFAULT_UNIT_COSTS["mail_design_fee"])
    digital_min = unit_costs.get("digital_minimum", DEFAULT_UNIT_COSTS["digital_minimum"])
    impressions = universe_size * 10  # 10 impressions per voter
    return {
        "canvassing": {
            "contacts":   universe_size,
            "unit_cost":  unit_costs.get("door_knock",    DEFAULT_UNIT_COSTS["door_knock"]),
            "total_cost": round(universe_size * unit_costs.get("door_knock", DEFAULT_UNIT_COSTS["door_knock"]), 2),
        },
        "phones": {
            "contacts":   universe_size,
            "unit_cost":  unit_costs.get("phone_call",    DEFAULT_UNIT_COSTS["phone_call"]),
            "total_cost": round(universe_size * unit_costs.get("phone_call", DEFAULT_UNIT_COSTS["phone_call"]), 2),
        },
        "text": {
            "contacts":   universe_size,
            "unit_cost":  unit_costs.get("text_message",  DEFAULT_UNIT_COSTS["text_message"]),
            "total_cost": round(universe_size * unit_costs.get("text_message", DEFAULT_UNIT_COSTS["text_message"]), 2),
        },
        "mail": {
            "contacts":   universe_size,
            "unit_cost":  unit_costs.get("mail_piece",    DEFAULT_UNIT_COSTS["mail_piece"]),
            "total_cost": round(design_fee + universe_size * unit_costs.get("mail_piece", DEFAULT_UNIT_COSTS["mail_piece"]), 2),
            "note":       f"Includes ${design_fee:,.0f} flat design fee",
        },
        "digital": {
            "contacts":   impressions,
            "unit_cost":  unit_costs.get("digital_cpm",   DEFAULT_UNIT_COSTS["digital_cpm"]),
            "total_cost": round(max(digital_min, impressions * unit_costs.get("digital_cpm", DEFAULT_UNIT_COSTS["digital_cpm"])), 2),
            "note":       "Impressions (10 per voter in universe)",
        },
    }


def _format_voter_file_narrative(
    universe_size: int,
    vf_label: str,
    unit_costs: dict,
    vf_budget: dict,
    budget_available: Optional[float],
    budget_program: Optional[dict],
) -> str:
    """Narrative memo for voter-file-mode budget estimates."""
    lines = [
        f"--- BUDGET ESTIMATE: {vf_label.upper()} | SOURCE: Voter File Universe + Unit Cost Analysis ---",
        "",
        "### Voter File Universe Budget",
        f"Budget projections are based on the uploaded voter file universe of **{universe_size:,} voters**.",
        "The estimates below show the cost to contact the full universe once per tactic.",
        "",
        "### Cost to Contact Full Universe",
    ]
    tactic_labels = {
        "canvassing": "Canvassing (door knock)",
        "phones":     "Phone calls",
        "text":       "Text messages",
        "mail":       "Mail pieces",
        "digital":    "Digital impressions",
    }
    for tactic, data in vf_budget.items():
        label = tactic_labels.get(tactic, tactic)
        note  = f" ({data['note']})" if data.get("note") else ""
        lines.append(
            f"- {label}: **${data['total_cost']:,.0f}** "
            f"({data['contacts']:,} contacts @ ${data['unit_cost']:.2f}/unit{note})"
        )

    dph = int(unit_costs.get("doors_per_hour", DEFAULT_UNIT_COSTS["doors_per_hour"]))
    lines += [
        "",
        "### Per-Contact Rates",
        f"- Door knock: ${unit_costs['door_knock']:.2f}/door ({dph} doors/hour avg.)",
        f"- Phone call: ${unit_costs['phone_call']:.2f}/call",
        f"- Text message: ${unit_costs['text_message']:.2f}/text",
        f"- Mail piece: ${unit_costs['mail_piece']:.2f}/piece + ${unit_costs.get('mail_design_fee', 500):,.0f} flat design fee",
        f"- Digital: ${unit_costs.get('digital_cpm', 0.02):.2f}/impression (${unit_costs.get('digital_minimum', 1000):,.0f} minimum)",
        "*(Rates sourced from tool_templates/costs.json — edit that file to reflect your market)*",
    ]

    if budget_available is not None and budget_program:
        lines += [
            "",
            f"### Budget-Constrained Program (${budget_available:,.0f} available)",
            "Recommended contact goals based on available budget:",
        ]
        tactic_label_map = {
            "door_knock":   "Door knocks",
            "phone_call":   "Phone calls",
            "text_message": "Text messages",
            "mail_piece":   "Mail pieces",
            "digital":      "Digital impressions",
        }
        for tactic, data in budget_program.items():
            label = tactic_label_map.get(tactic, tactic)
            note  = f" ({data['note']})" if data.get("note") else ""
            lines.append(
                f"- {label}: {data['contacts']:,} contacts "
                f"(${data['budget_allocated']:,.0f} @ ${data['unit_cost']:.2f}/unit{note})"
            )
        total_contacts = sum(d["contacts"] for d in budget_program.values())
        lines.append(f"\n**Total contacts: {total_contacts:,}**")

    lines.append("")
    return "\n".join(lines)


def _format_narrative(
    district_label: str,
    mode: str,
    fec_result: Optional[dict],
    category_breakdown: Optional[dict],
    unit_costs: dict,
    budget_available: Optional[float],
    budget_program: Optional[dict],
    comparable_cycles: list,
    district_type: str,
) -> str:
    """
    Build a narrative budget memo for research_results in the standard memo format
    used by other agents (so the synthesizer can incorporate it directly).
    """
    lines = [
        f"--- BUDGET ESTIMATE: {district_label.upper()} | SOURCE: FEC + Unit Cost Analysis ---"
    ]

    if mode in ("historical", "hybrid") and fec_result and fec_result.get("avg_disbursements", 0) > 0:
        avg = fec_result["avg_disbursements"]
        sampled = fec_result["candidates_sampled"]
        cycles  = fec_result["cycles_found"]
        lines += [
            "",
            f"### Historical Spending (FEC — {district_label})",
            f"Based on {sampled} candidate{'s' if sampled != 1 else ''} across "
            f"{len(cycles)} comparable election cycle{'s' if len(cycles) != 1 else ''} "
            f"({', '.join(str(c) for c in cycles)}), the average total campaign "
            f"disbursement for this race type was **${avg:,.0f}**.",
            "",
            "**Estimated spending by category** (based on industry averages for "
            f"{district_type.replace('_', ' ').title()} races):",
        ]
        if category_breakdown:
            for cat, amt in category_breakdown.items():
                lines.append(f"- {cat.title()}: ${amt:,.0f}")

    elif mode == "unit_cost_only":
        lines += [
            "",
            "### Spending Estimate",
            f"FEC data is not available for {district_label} (state legislative races are not "
            "reported to the FEC). Budget projections below are based on unit cost estimates only.",
        ]

    dph = int(unit_costs.get("doors_per_hour", DEFAULT_UNIT_COSTS["doors_per_hour"]))
    lines += [
        "",
        "### Per-Contact Rates",
        "The following cost-per-contact rates are used for budget projections:",
        f"- Door knock: ${unit_costs['door_knock']:.2f} per door ({dph} doors/hour avg.)",
        f"- Phone call: ${unit_costs['phone_call']:.2f} per call",
        f"- Text message: ${unit_costs['text_message']:.2f} per text",
        f"- Mail piece: ${unit_costs['mail_piece']:.2f} per piece "
        f"+ ${unit_costs.get('mail_design_fee', 500):,.0f} flat design fee",
        f"- Digital: ${unit_costs.get('digital_cpm', 0.02):.2f} per impression "
        f"(${unit_costs.get('digital_minimum', 1000):,.0f} minimum per flight)",
        "*(Rates sourced from tool_templates/costs.json — edit that file to reflect your market)*",
    ]

    if budget_available is not None and budget_program:
        lines += [
            "",
            f"### Budget-Constrained Program (${budget_available:,.0f} available)",
            "Recommended contact goals based on available budget:",
        ]
        tactic_labels = {
            "door_knock":   "Door knocks",
            "phone_call":   "Phone calls",
            "text_message": "Text messages",
            "mail_piece":   "Mail pieces",
            "digital":      "Digital impressions",
        }
        for tactic, data in budget_program.items():
            label = tactic_labels.get(tactic, tactic)
            note  = f" ({data['note']})" if data.get("note") else ""
            lines.append(
                f"- {label}: {data['contacts']:,} contacts "
                f"(${data['budget_allocated']:,.0f} @ ${data['unit_cost']:.2f}/unit{note})"
            )
        total_contacts = sum(d["contacts"] for d in budget_program.values())
        lines.append(f"\n**Total contacts: {total_contacts:,}**")

    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Node
# ---------------------------------------------------------------------------

def finance_node(state: AgentState) -> dict:
    """
    Accountant agent LangGraph node.

    Reads from state:
      - structured_data: geographic context (state_fips, district_type, district_id)
                         and win number data (projected_turnout, voter_universe_cvap)
      - query:           checked for budget amounts (e.g. "I have $50,000")

    Writes to state:
      - structured_data:  budget breakdown dict (appended)
      - research_results: narrative budget memo (appended)
      - active_agents:    ["finance"]
      - errors:           FEC API failures (non-fatal)
    """
    errors_out = []

    # -----------------------------------------------------------------------
    # 1. Resolve geographic context from the whiteboard
    # -----------------------------------------------------------------------
    prior = next(
        (
            d for d in state.get("structured_data", [])
            if d.get("state_fips") and d.get("district_type") and d.get("district_id")
        ),
        None,
    )

    if prior:
        state_fips    = prior["state_fips"]
        district_type = prior["district_type"]
        district_id   = prior["district_id"]
        target_year   = prior.get("target_year", 2026)
    else:
        # -----------------------------------------------------------------------
        # Voter file fallback: no geographic context but voter file data present.
        # Skip FEC / district lookup entirely; estimate from universe size.
        # -----------------------------------------------------------------------
        vf_entry = next(
            (d for d in state.get("structured_data", []) if d.get("agent") == "voter_file"),
            None,
        )
        if vf_entry:
            universe_size = (
                vf_entry.get("total_voters")
                or vf_entry.get("summary", {}).get("total_voters", 0)
            )
            unit_costs_vf = _load_unit_costs()

            if not universe_size:
                return {
                    "research_results": [
                        "--- BUDGET ESTIMATE | SOURCE: Voter File ---\n\n"
                        "Voter file data was found but total_voters is missing or zero. "
                        "Cannot estimate contact costs without a universe size.\n"
                    ],
                    "active_agents": ["cost_calculator"],
                    "errors":        ["FinanceAgent: voter_file entry missing total_voters — skipping budget estimate."],
                }

            vf_budget = _build_voter_file_budget(universe_size, unit_costs_vf)

            # Extract budget from query if the user specified one
            budget_available_vf: Optional[float] = None
            _bq = state.get("query", "").strip()
            if _bq:
                try:
                    _llm_vf = ChatOpenAI(model="gpt-4o", temperature=0,
                                         openai_api_key=os.environ["OPENAI_API_KEY"])
                    _br = _llm_vf.invoke(
                        f'Does this query mention a specific budget? If yes return the number only. '
                        f'If no, return NONE.\nQuery: "{_bq}"\nBUDGET:'
                    ).content.strip()
                    if _br.upper() != "NONE":
                        budget_available_vf = float(re.sub(r"[^\d.]", "", _br) or "0") or None
                except Exception:
                    pass

            budget_program_vf = (
                _build_budget_program(budget_available_vf, unit_costs_vf)
                if budget_available_vf else None
            )

            narrative_vf = _format_voter_file_narrative(
                universe_size=universe_size,
                vf_label="Voter File Universe",
                unit_costs=unit_costs_vf,
                vf_budget=vf_budget,
                budget_available=budget_available_vf,
                budget_program=budget_program_vf,
            )

            logger.info(
                f"FinanceAgent: voter-file mode | universe={universe_size:,} | "
                f"budget={'${:,.0f}'.format(budget_available_vf) if budget_available_vf else 'not specified'}"
            )

            # Paid-media estimate (file 07): triggered when a budget is set AND
            # either the user asked for paid media OR the budget is large
            # enough that digital is intrinsic to the program (>= $25K).
            paid_media_vf = None
            paid_media_section_vf = ""
            if budget_available_vf and (
                budget_available_vf >= 25_000
                or query_mentions_paid_media(state.get("query", ""))
            ):
                paid_media_vf = estimate_paid_media(
                    budget=budget_available_vf,
                    query=state.get("query", ""),
                    language_intent=state.get("language_intent"),
                    district_label="Voter File Universe",
                    target_universe=universe_size,
                )
                if paid_media_vf:
                    paid_media_section_vf = format_paid_media_section(paid_media_vf)

            narrative_combined_vf = (
                narrative_vf + "\n\n" + paid_media_section_vf
                if paid_media_section_vf else narrative_vf
            )

            structured_vf = {
                "agent":          "finance",
                "mode":           "voter_file",
                "data_source":    "unit_cost_only",
                "universe_size":  universe_size,
                "unit_costs":     unit_costs_vf,
                "budget_available": budget_available_vf,
                "vf_budget":      vf_budget,
                "budget_program": budget_program_vf,
            }
            if paid_media_vf:
                structured_vf["paid_media"] = paid_media_vf

            return {
                "structured_data": [structured_vf],
                "research_results": [narrative_combined_vf],
                "active_agents":    ["cost_calculator"],
            }

        # -----------------------------------------------------------------------
        # No voter file data — try to extract geographic context from query via LLM
        # -----------------------------------------------------------------------
        query = state.get("query", "").strip()
        if not query:
            unit_costs_fb = _load_unit_costs()
            return {
                "research_results": [_format_narrative(
                    district_label="Unspecified District",
                    mode="unit_cost_only",
                    fec_result=None, category_breakdown=None,
                    unit_costs=unit_costs_fb,
                    budget_available=None, budget_program=None,
                    comparable_cycles=[], district_type="congressional",
                )],
                "active_agents": ["cost_calculator"],
                "errors":        ["FinanceAgent: no query or voter file context — returning unit cost rates only."],
            }

        llm = ChatOpenAI(
            model="gpt-4o",
            temperature=0,
            openai_api_key=os.environ["OPENAI_API_KEY"],
        )
        extraction_prompt = f"""
Extract electoral district information from this query. Return ONLY these lines, no extra text.

Query: "{query}"

STATE: [full state name or abbreviation]
DISTRICT_TYPE: [congressional | state_senate | state_house | senate]
DISTRICT_NUM: [integer district number, or 0 for at-large, or "statewide" for senate]
TARGET_YEAR: [4-digit election year, default 2026]
"""
        try:
            raw = llm.invoke(extraction_prompt).content.strip()
        except Exception as e:
            return {
                "errors":        [f"FinanceAgent: LLM extraction failed — {e}"],
                "active_agents": ["cost_calculator"],
            }

        params: dict = {}
        for line in raw.splitlines():
            if ":" in line:
                key, _, val = line.partition(":")
                params[key.strip().upper()] = val.strip().strip('"')

        state_name = params.get("STATE", "")
        state_fips = GeographyStandardizer.STATE_FIPS.get(state_name.lower())
        if not state_fips:
            unit_costs_fb = _load_unit_costs()
            warn_msg = f"FinanceAgent: could not resolve state for '{state_name}' — returning unit cost rates only."
            logger.warning(warn_msg)
            return {
                "research_results": [_format_narrative(
                    district_label=f"Unspecified District ({state_name or 'unknown state'})",
                    mode="unit_cost_only",
                    fec_result=None, category_breakdown=None,
                    unit_costs=unit_costs_fb,
                    budget_available=None, budget_program=None,
                    comparable_cycles=[], district_type="congressional",
                )],
                "structured_data": [{"agent": "finance", "mode": "unit_cost_only", "data_source": "none"}],
                "active_agents":   ["cost_calculator"],
                "errors":          [warn_msg],
            }

        district_type = params.get("DISTRICT_TYPE", "congressional").lower()

        try:
            target_year = int(params.get("TARGET_YEAR", 2026))
        except ValueError:
            target_year = 2026

        if district_type == "senate":
            district_id = "statewide"
        else:
            dist_num_raw = params.get("DISTRICT_NUM", "0")
            try:
                dist_num = int(dist_num_raw)
            except (ValueError, TypeError):
                return {
                    "errors":        [f"FinanceAgent: Could not parse district number from '{dist_num_raw}'."],
                    "active_agents": ["cost_calculator"],
                }
            geoid = GeographyStandardizer.convert_to_geoid(state_name, dist_num, district_type)
            if isinstance(geoid, dict):
                return {
                    "errors":        [f"FinanceAgent: {geoid.get('error')}"],
                    "active_agents": ["cost_calculator"],
                }
            district_id = geoid

    # -----------------------------------------------------------------------
    # 2. Extract budget from query (if provided)
    # -----------------------------------------------------------------------
    llm = ChatOpenAI(
        model="gpt-4o",
        temperature=0,
        openai_api_key=os.environ["OPENAI_API_KEY"],
    )

    budget_available: Optional[float] = None
    _budget_query = state.get("query", "").strip()
    if not _budget_query:
        logger.debug("FinanceAgent: query is empty — skipping budget extraction, defaulting to None.")
    else:
        budget_prompt = f"""
Does the following query mention a specific campaign budget or available funds?
If yes, return the dollar amount as a plain number (e.g. 50000).
If no budget is mentioned, return NONE.

Query: "{_budget_query}"

BUDGET: [number or NONE]
"""
        try:
            budget_raw = llm.invoke(budget_prompt).content.strip()
            match = re.search(r"BUDGET:\s*([\d,\.]+|NONE)", budget_raw, re.IGNORECASE)
            if match and match.group(1).upper() != "NONE":
                budget_available = float(re.sub(r"[,]", "", match.group(1)))
        except Exception as e:
            logger.warning(f"FinanceAgent: Budget extraction failed — {e}")

    # -----------------------------------------------------------------------
    # 3. Load unit costs (from tool_templates/ or defaults)
    # -----------------------------------------------------------------------
    unit_costs = _load_unit_costs()

    # -----------------------------------------------------------------------
    # 4. Determine mode and fetch FEC data (federal races only)
    # -----------------------------------------------------------------------
    comparable_cycles = _pick_cycles(target_year)
    state_abbr = _FIPS_TO_ABBR.get(state_fips, "")
    office = FEC_OFFICE_MAP.get(district_type)

    fec_result: Optional[dict] = None
    category_breakdown: Optional[dict] = None
    mode = "unit_cost_only"

    if office and state_abbr:
        # Derive the district number suffix for FEC calls
        if district_type == "senate":
            dist_suffix = "00"
        elif district_type == "congressional":
            dist_suffix = district_id[len(state_fips):]  # "5107" → "07"
        else:
            dist_suffix = "00"

        fec_result = _fetch_fec_average(
            state_abbr=state_abbr,
            district_num=dist_suffix,
            office=office,
            cycles=comparable_cycles,
        )

        if fec_result.get("error"):
            errors_out.append(f"FinanceAgent: FEC — {fec_result['error']}")
            mode = "unit_cost_only"
        elif fec_result.get("avg_disbursements", 0) > 0:
            category_breakdown = _build_category_breakdown(
                fec_result["avg_disbursements"], district_type
            )
            mode = "historical" if budget_available is None else "hybrid"
    else:
        # State legislative race — no FEC coverage
        logger.info(
            f"FinanceAgent: district_type '{district_type}' has no FEC coverage; "
            "running in unit-cost-only mode."
        )

    # -----------------------------------------------------------------------
    # 5. Build budget-constrained program if a budget was provided
    # -----------------------------------------------------------------------
    budget_program: Optional[dict] = None
    if budget_available is not None:
        budget_program = _build_budget_program(budget_available, unit_costs)

    # -----------------------------------------------------------------------
    # 6. Build human-readable district label
    # -----------------------------------------------------------------------
    district_label = (
        f"{district_type.replace('_', ' ').title()} {district_id}"
        if district_id != "statewide"
        else f"Statewide Senate — {state_abbr}"
    )

    # -----------------------------------------------------------------------
    # 7. Format narrative memo for research_results
    # -----------------------------------------------------------------------
    narrative = _format_narrative(
        district_label=district_label,
        mode=mode,
        fec_result=fec_result,
        category_breakdown=category_breakdown,
        unit_costs=unit_costs,
        budget_available=budget_available,
        budget_program=budget_program,
        comparable_cycles=comparable_cycles,
        district_type=district_type,
    )

    logger.info(
        f"FinanceAgent: mode={mode} | district={district_label} | "
        f"budget={'${:,.0f}'.format(budget_available) if budget_available else 'not specified'}"
    )

    # -----------------------------------------------------------------------
    # 7b. Paid-media plan from file 07 (CPMs, frequency caps, channel mix)
    # Triggered when a budget is set AND the user asked for paid media OR the
    # budget is large enough that digital is intrinsic (>= $25K).
    # -----------------------------------------------------------------------
    paid_media = None
    paid_media_section = ""
    if budget_available and (
        budget_available >= 25_000
        or query_mentions_paid_media(state.get("query", ""))
    ):
        # Use win-number-derived persuadable universe when available; falls back
        # to projected_turnout, then None (no saturation cap applied).
        wn_entry = next(
            (d for d in state.get("structured_data", []) if d.get("agent") == "win_number"),
            None,
        )
        target_universe_pm = None
        if wn_entry:
            target_universe_pm = (
                wn_entry.get("persuadable_universe")
                or wn_entry.get("projected_turnout")
                or wn_entry.get("voter_universe_cvap")
            )
        paid_media = estimate_paid_media(
            budget=budget_available,
            query=state.get("query", ""),
            language_intent=state.get("language_intent"),
            district_label=district_label,
            target_universe=target_universe_pm,
        )
        if paid_media:
            paid_media_section = format_paid_media_section(paid_media)

    narrative_combined = (
        narrative + "\n\n" + paid_media_section
        if paid_media_section else narrative
    )

    # -----------------------------------------------------------------------
    # 8. Write to whiteboard
    # -----------------------------------------------------------------------
    structured_entry = {
        "agent":              "finance",
        "state_fips":         state_fips,
        "district_type":      district_type,
        "district_id":        district_id,
        "mode":               mode,
        "comparable_cycles":  comparable_cycles,
        "unit_costs":         unit_costs,
        "budget_available":   budget_available,
        "full_program_estimate": {
            "total":         round(fec_result["avg_disbursements"], 2) if fec_result else None,
            **(category_breakdown or {}),
        } if fec_result and fec_result.get("avg_disbursements") else None,
        "budget_program":     budget_program,
        "fec_candidates_sampled": fec_result.get("candidates_sampled", 0) if fec_result else 0,
        "data_source": (
            "fec" if mode == "historical"
            else "fec+unit_cost" if mode == "hybrid"
            else "unit_cost_only"
        ),
    }
    if paid_media:
        structured_entry["paid_media"] = paid_media

    result = {
        "structured_data":  [structured_entry],
        "research_results": [narrative_combined],
        "active_agents":    ["cost_calculator"],
    }
    if errors_out:
        result["errors"] = errors_out

    return result
