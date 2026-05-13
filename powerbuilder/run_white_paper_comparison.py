#!/usr/bin/env python3
"""
run_white_paper_comparison.py

Sequential LLM provider white paper comparison for Powerbuilder.

Runs the full planning pipeline against OpenAI, Anthropic, and Gemini (plus
ChangeAgent when CHANGEAGENT_API_KEY is set) using:

    Query:    "Write me a complete political program plan for Arizona's 6th
               Congressional District targeting young and Hispanic voters in 2026."
    Fallback: Virginia 7th Congressional District if AZ-06 crosswalk unavailable.

Output
------
  exports/llm_white_paper_{timestamp}.md          — full white paper
  exports/white_paper_openai_{timestamp}.md        — raw OpenAI final_answer
  exports/white_paper_anthropic_{timestamp}.md     — raw Anthropic final_answer
  exports/white_paper_gemini_{timestamp}.md        — raw Gemini final_answer

Run from project root:
    python run_white_paper_comparison.py
"""

import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

# load_dotenv MUST precede all API-key-dependent imports
from dotenv import load_dotenv
load_dotenv()

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

QUERY = (
    "Write me a complete political program plan for Arizona's 6th Congressional District "
    "targeting young and Hispanic voters in 2026."
)

PRIMARY_DISTRICT  = {"state_fips": "04", "district_id": "0406", "label": "AZ-06 (Arizona 6th)"}
FALLBACK_DISTRICT = {"state_fips": "51", "district_id": "5107", "label": "VA-07 (Virginia 7th)"}

PROVIDERS = ["openai", "anthropic", "gemini"]

EXPORTS_DIR = ROOT / "exports"
EXPORTS_DIR.mkdir(exist_ok=True)

CHANGEAGENT_API_KEY = os.getenv("CHANGEAGENT_API_KEY", "").strip()
CHANGEAGENT_URL     = "https://api.changeagent.com/v1/district/{state_fips}/{district_id}/benchmarks"

# Non-fatal error patterns — don't flag these as run failures
NON_FATAL_PATTERNS = [
    "PrecinctsAgent: Census API",
    "Census API failure",
    "MEDSL",
    "FEC",
    "election_results",
    "No election data",
    "crosswalk",
    "coverage_note",
]


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def _fmt_time(seconds) -> str:
    if seconds is None:
        return "N/A"
    m, s = divmod(int(float(seconds)), 60)
    return f"{m}m {s}s" if m else f"{s}s"


def _fmt_num(v) -> str:
    try:
        return f"{int(v):,}"
    except (TypeError, ValueError):
        return str(v) if v is not None else "N/A"


# ---------------------------------------------------------------------------
# Structured-data extractors
# ---------------------------------------------------------------------------

def _find_entry(structured_data: list, agent: str) -> dict | None:
    for entry in structured_data or []:
        if isinstance(entry, dict) and entry.get("agent") == agent:
            return entry
    return None


def _find_entries(structured_data: list, agent: str) -> list[dict]:
    return [e for e in (structured_data or []) if isinstance(e, dict) and e.get("agent") == agent]


def _has_coverage_note(structured_data: list) -> bool:
    for entry in structured_data or []:
        if isinstance(entry, dict) and entry.get("agent") == "precincts" and entry.get("coverage_note"):
            return True
    return False


def _extract_research_sources(research_results: list) -> list[str]:
    sources = []
    for item in research_results or []:
        text = str(item)
        # Try bracketed source label first: [Source Name | date]
        m = re.search(r'\[([^\]]{4,120}?)(?:\s*\|[^\]]*)?]', text)
        if m:
            sources.append(m.group(1).strip())
        else:
            first_line = text.strip().split('\n')[0][:80].strip()
            if first_line:
                sources.append(first_line)
    return sources


# ---------------------------------------------------------------------------
# LLM synthesis helper — always OpenAI GPT-4o for white paper analysis
# ---------------------------------------------------------------------------

def _llm_analyze(prompt: str) -> str:
    try:
        from langchain_openai import ChatOpenAI
        llm = ChatOpenAI(
            model="gpt-4o",
            temperature=0.3,
            openai_api_key=os.environ["OPENAI_API_KEY"],
        )
        return llm.invoke(prompt).content.strip()
    except Exception as exc:
        return f"*(Analysis unavailable: {exc})*"


# ---------------------------------------------------------------------------
# ChangeAgent API call
# ---------------------------------------------------------------------------

def _call_changeagent(state_fips: str, district_id: str) -> dict:
    import requests
    url = CHANGEAGENT_URL.format(state_fips=state_fips, district_id=district_id)
    try:
        resp = requests.get(
            url,
            headers={"Authorization": f"Bearer {CHANGEAGENT_API_KEY}"},
            timeout=15,
        )
        resp.raise_for_status()
        return {"url": url, "data": resp.json(), "error": None}
    except Exception as exc:
        status = getattr(getattr(exc, "response", None), "status_code", None)
        return {
            "url": url,
            "data": None,
            "error": f"HTTP {status}: {exc}" if status else str(exc),
        }


# ---------------------------------------------------------------------------
# Per-provider pipeline runner
# ---------------------------------------------------------------------------

def run_provider(provider: str) -> dict:
    from chat.agents.manager import run_query

    print(f"  Running {provider.title()}...", end="", flush=True)
    t0 = time.perf_counter()
    state: dict = {}
    fatal_error: str | None = None

    try:
        state = run_query(
            query=QUERY,
            org_namespace="general",
            output_format="markdown",
            llm_provider=provider,
        )
    except Exception as exc:
        fatal_error = str(exc)

    elapsed = time.perf_counter() - t0

    if fatal_error:
        print(f" FAILED in {_fmt_time(elapsed)} — {fatal_error[:60]}")
    else:
        n_errors = len(state.get("errors", []))
        print(f" done in {_fmt_time(elapsed)}"
              + (f" ({n_errors} non-fatal errors)" if n_errors else ""))

    return {
        "provider":         provider,
        "elapsed_s":        elapsed,
        "final_answer":     state.get("final_answer", ""),
        "research_results": state.get("research_results", []),
        "active_agents":    state.get("active_agents", []),
        "errors":           state.get("errors", []),
        "structured_data":  state.get("structured_data", []),
        "generated_file":   state.get("generated_file_path"),
        "error":            fatal_error,
    }


# ---------------------------------------------------------------------------
# White paper section builders
# ---------------------------------------------------------------------------

def _build_executive_summary(results: list[dict], district: dict) -> str:
    run_lines = []
    for r in results:
        if r.get("error"):
            run_lines.append(f"- {r['provider'].title()}: FAILED — {r['error']}")
        else:
            run_lines.append(
                f"- {r['provider'].title()} ({_fmt_time(r['elapsed_s'])}): "
                f"{len(r['final_answer'])} chars, "
                f"agents=[{', '.join(r['active_agents'])}], "
                f"{len(r['errors'])} non-fatal errors"
            )

    prompt = (
        f"You are analyzing three AI political planning tools (OpenAI gpt-4o, "
        f"Anthropic claude-sonnet-4-5, Gemini gemini-2.5-flash). Each generated a "
        f"complete political program plan for {district['label']}, targeting young and "
        f"Hispanic voters in 2026.\n\n"
        f"Run results:\n" + "\n".join(run_lines) + "\n\n"
        "Write a 3–4 sentence Executive Summary for a white paper comparing their outputs. "
        "Focus on the most important differentiator across providers. Be specific — reference "
        "speed, completeness, and any notable divergence. Do not include a header."
    )
    return _llm_analyze(prompt)


def _build_research_retrieval(results: list[dict]) -> list[str]:
    lines: list[str] = []
    source_sets: dict[str, set[str]] = {}

    for r in results:
        sources = _extract_research_sources(r["research_results"]) if not r.get("error") else []
        source_sets[r["provider"]] = set(sources)

    common = set.intersection(*source_sets.values()) if len(source_sets) >= 2 else set()
    unique_to: dict[str, set[str]] = {}
    if len(source_sets) >= 2:
        for p, s in source_sets.items():
            others = set.union(*(v for k, v in source_sets.items() if k != p))
            unique_to[p] = s - others

    for r in results:
        p = r["provider"]
        lines += [f"### {p.title()}", ""]
        if r.get("error"):
            lines += [f"*Run failed: {r['error']}*", ""]
            continue

        sources = _extract_research_sources(r["research_results"])
        lines += [
            f"**Documents retrieved:** {len(r['research_results'])}  ",
            f"**Unique sources:** {len(source_sets[p])}  ",
            "",
        ]

        if sources:
            lines += ["| # | Source |", "|---|--------|"]
            for i, src in enumerate(sources[:20], 1):
                lines.append(f"| {i} | {src} |")
            lines.append("")

        bp_found = [s for s in sources if "best_practice" in s.lower() or "best practice" in s.lower()]
        if bp_found:
            lines.append(f"**Best practices files retrieved:** {', '.join(bp_found[:3])}")
        else:
            lines.append("**Best practices files:** None detected in top sources.")
        lines.append("")

        p_unique = unique_to.get(p, set())
        if p_unique:
            lines.append(f"**Unique to {p.title()} (not retrieved by other providers):**")
            for s in sorted(p_unique)[:5]:
                lines.append(f"  - {s}")
            lines.append("")

    if common:
        lines += [f"**Retrieved by all providers ({len(common)} sources):**"]
        for s in sorted(common)[:10]:
            lines.append(f"  - {s}")
        lines.append("")

    return lines


def _build_win_number(results: list[dict]) -> list[str]:
    lines = [
        "| Provider | Win Number | Projected Turnout | CVAP | Avg Turnout % | Data Notes |",
        "|----------|------------|-------------------|------|---------------|------------|",
    ]
    win_numbers: dict[str, int | None] = {}

    for r in results:
        p = r["provider"]
        if r.get("error"):
            lines.append(f"| {p.title()} | *run failed* | — | — | — | — |")
            win_numbers[p] = None
            continue

        wn_entry = _find_entry(r["structured_data"], "win_number")
        if not wn_entry:
            lines.append(f"| {p.title()} | *not in structured_data* | — | — | — | — |")
            win_numbers[p] = None
            continue

        win_n   = wn_entry.get("win_number")
        turnout = wn_entry.get("projected_turnout")
        cvap    = wn_entry.get("voter_universe_cvap")
        pct     = wn_entry.get("avg_turnout_pct")
        notes   = (wn_entry.get("data_notes") or "")[:60]
        pct_str = f"{float(pct)*100:.1f}%" if pct is not None else "N/A"

        lines.append(
            f"| {p.title()} | {_fmt_num(win_n)} | {_fmt_num(turnout)} | "
            f"{_fmt_num(cvap)} | {pct_str} | {notes} |"
        )
        win_numbers[p] = win_n

    lines.append("")

    values = [v for v in win_numbers.values() if v is not None]
    if not values:
        lines.append("**Result:** No win numbers extracted — check structured_data keys.")
    elif len(set(values)) == 1:
        lines.append(
            f"**Result:** All providers calculated the same win number ({_fmt_num(values[0])}) — "
            "as expected, since this is deterministic data from Census CVAP + master election CSVs."
        )
    else:
        lines.append(
            f"**Discrepancy detected:** Win numbers differ across providers ({win_numbers}). "
            "This is unexpected since the calculation is deterministic. "
            "Verify district resolution — providers may have resolved to different GEOIDs."
        )

    return lines


def _build_precinct_targeting(results: list[dict]) -> list[str]:
    lines: list[str] = []
    top_precincts: dict[str, list[str]] = {}

    for r in results:
        p = r["provider"]
        lines += [f"### {p.title()}", ""]

        if r.get("error"):
            lines += [f"*Run failed: {r['error']}*", ""]
            continue

        if _has_coverage_note(r["structured_data"]):
            lines += [
                "*Precinct-level crosswalk data not available for this district. "
                "Geographic targeting section used a coverage note instead.*",
                "",
            ]
            top_precincts[p] = []
            continue

        precinct_entry = _find_entry(r["structured_data"], "precincts")
        precincts = (precinct_entry or {}).get("precincts", [])

        if not precincts:
            lines += ["*No precincts returned in structured_data.*", ""]
            top_precincts[p] = []
            continue

        top5 = precincts[:5]
        names = []
        lines += [f"**Top {len(top5)} precincts:**", "", "| Rank | Precinct | Score |"]
        lines.append("|------|----------|-------|")
        for i, prec in enumerate(top5, 1):
            name = (
                prec.get("precinct_name")
                or prec.get("precinct")
                or prec.get("name")
                or f"Precinct {i}"
            )
            score = prec.get("score") or prec.get("target_score") or "—"
            lines.append(f"| {i} | {name} | {score} |")
            names.append(str(name))
        lines.append("")
        top_precincts[p] = names

    # Cross-provider consistency check
    ranked = {p: ns for p, ns in top_precincts.items() if ns}
    if len(ranked) >= 2:
        all_top1 = [ns[0] for ns in ranked.values()]
        if len(set(all_top1)) == 1:
            lines.append(
                f"**Consistency:** All providers ranked `{all_top1[0]}` first — "
                "expected since precinct scoring is deterministic."
            )
        else:
            lines.append(
                "**Ranking divergence:** Top precinct differs across providers. "
                f"{', '.join(f'{p}: {ns[0]}' for p, ns in ranked.items())} — "
                "this may reflect district resolution differences, not LLM synthesis."
            )
        lines.append("")

    return lines


def _build_messaging_quality(results: list[dict]) -> list[str]:
    excerpts: dict[str, str] = {}
    for r in results:
        p = r["provider"]
        if r.get("error") or not r["final_answer"]:
            excerpts[p] = "*(run failed or no output)*"
            continue
        text = r["final_answer"]
        m = re.search(
            r'(## (?:Messaging|Message|Script|Communication|Canvass).{0,60}\n)(.*?)(?=\n## |\Z)',
            text, re.DOTALL | re.IGNORECASE,
        )
        excerpts[p] = (m.group(0) if m else text)[:3000]

    excerpt_block = "\n\n---\n\n".join(
        f"### {p.upper()}\n{exc}" for p, exc in excerpts.items()
    )

    prompt = (
        "You are a senior political strategist reviewing three AI-generated political plans "
        "for AZ-06 (Arizona's 6th Congressional District) targeting young (18–29) and "
        "Hispanic voters in 2026.\n\n"
        "Analyze the messaging strategy excerpts below and write a structured comparison "
        "(300–400 words) covering four dimensions:\n"
        "1. **Specificity** — does each provider reference actual AZ-06 demographics or use generic language?\n"
        "2. **Demographic nuance** — does it treat youth and Hispanic messaging as distinct tracks?\n"
        "3. **Contrast messaging quality** — how strong are the opponent contrast angles?\n"
        "4. **Script quality** — if a script pack is present, is the copy voter-ready?\n\n"
        "Name which providers perform better on each dimension. Be specific.\n\n"
        f"Excerpts:\n\n{excerpt_block}\n\n"
        "Write as 4 short paragraphs (one per dimension). No header."
    )
    return [_llm_analyze(prompt), ""]


def _build_speculation_behavior(results: list[dict]) -> list[str]:
    excerpts: dict[str, str] = {}
    for r in results:
        p = r["provider"]
        if r.get("error") or not r["final_answer"]:
            excerpts[p] = "*(run failed)*"
            continue
        text = r["final_answer"]

        opp_m = re.search(
            r'(## (?:Opposition|Republican|Opponent|Incumbent|Juan).{0,60}\n)(.*?)(?=\n## |\Z)',
            text, re.DOTALL | re.IGNORECASE,
        )
        opp_excerpt = (opp_m.group(0) if opp_m else "")[:2000]

        uncertainty_lines = [
            line.strip() for line in text.split('\n')
            if any(w in line.lower() for w in [
                "data not available", "limited data", "unknown", "not found",
                "unable to", "no data", "not yet", "pending", "ciscomani",
                "juan ciscomani", "estimated", "assume", "likely", "probably",
                "party affiliation", "medsl", "historical data",
            ])
        ]
        excerpts[p] = (
            f"Opposition research section:\n{opp_excerpt}\n\n"
            f"Uncertainty / data-gap language (sampled):\n"
            + "\n".join(uncertainty_lines[:15])
        )

    error_ctx = "\n".join(
        f"{r['provider'].title()} pipeline errors: " + "; ".join(r.get("errors", [])[:3])
        for r in results if r.get("errors")
    )

    excerpt_block = "\n\n---\n\n".join(
        f"### {p.upper()}\n{exc}" for p, exc in excerpts.items()
    )

    prompt = (
        "You are analyzing three AI political planning tools for their speculation behavior. "
        "AZ-06 in 2026 is held by Republican Juan Ciscomani (incumbent). "
        "Well-calibrated models should name known facts confidently and clearly acknowledge "
        "uncertainty when data is missing.\n\n"
        "Review the excerpts and write a structured analysis (300–400 words) covering:\n"
        "1. **Opposition research handling** — does each provider name Ciscomani confidently or hedge?\n"
        "2. **MEDSL data gaps** — does it acknowledge missing party-level historical data, or invent it?\n"
        "3. **Overall calibration rating** for each provider: Underconfident / Calibrated / Overconfident.\n\n"
        f"Provider excerpts:\n\n{excerpt_block}\n\n"
        f"Known real pipeline errors (actual data gaps):\n{error_ctx}\n\n"
        "Write as 3 paragraphs (one per dimension). No header."
    )
    return [_llm_analyze(prompt), ""]


def _build_scorecard(results: list[dict]) -> list[str]:
    run_summaries = "\n".join(
        f"- {r['provider'].title()} ({r['provider']}): "
        f"wall_clock={_fmt_time(r['elapsed_s'])}, "
        f"answer_chars={len(r.get('final_answer',''))}, "
        f"agents_run={len(r.get('active_agents', []))}, "
        f"pipeline_errors={len(r.get('errors', []))}, "
        f"fatal={'yes' if r.get('error') else 'no'}"
        for r in results
    )

    prompt = (
        "You are scoring three AI political planning tools on 1–5 scales. "
        "Based on the run data below, return ONLY a valid JSON array — no markdown fences, "
        "no explanation — with this exact structure:\n"
        '[\n'
        '  {\n'
        '    "provider": "openai",\n'
        '    "research_depth": 4, "research_reason": "brief reason under 60 chars",\n'
        '    "factual_accuracy": 4, "factual_reason": "...",\n'
        '    "messaging_specificity": 3, "messaging_reason": "...",\n'
        '    "writing_quality": 4, "writing_reason": "...",\n'
        '    "appropriate_confidence": 3, "confidence_reason": "...",\n'
        '    "speed_score": 3, "speed_reason": "..."\n'
        '  }, ...\n'
        ']\n\n'
        "Speed scoring guide: <45s=5, 45–90s=4, 90–180s=3, 180–300s=2, >300s or error=1.\n\n"
        f"Run data:\n{run_summaries}\n\n"
        "Return ONLY the JSON array."
    )
    raw = _llm_analyze(prompt)

    try:
        clean = re.sub(r'^```(?:json)?\s*', '', raw.strip())
        clean = re.sub(r'\s*```$', '', clean.strip())
        scores = json.loads(clean)
    except Exception:
        return [
            "*(Score table parsing failed — raw output below)*", "",
            f"```\n{raw}\n```", "",
        ]

    dims = [
        ("research_depth",         "research_reason",    "Research Depth"),
        ("factual_accuracy",       "factual_reason",      "Factual Accuracy"),
        ("messaging_specificity",  "messaging_reason",    "Messaging Specificity"),
        ("writing_quality",        "writing_reason",      "Writing Quality"),
        ("appropriate_confidence", "confidence_reason",   "Appropriate Confidence"),
        ("speed_score",            "speed_reason",        "Speed"),
    ]
    providers_in = [s["provider"] for s in scores]

    lines = [
        "| Dimension | " + " | ".join(p.title() for p in providers_in) + " |",
        "|-----------|" + "|".join(["--------"] * len(providers_in)) + "|",
    ]
    for key, reason_key, label in dims:
        cells = []
        for s in scores:
            val = s.get(key, "—")
            reason = (s.get(reason_key) or "")[:55]
            cells.append(f"**{val}/5** {reason}")
        lines.append("| " + label + " | " + " | ".join(cells) + " |")

    lines.append("")
    return lines


def _build_recommendations(results: list[dict]) -> list[str]:
    run_summary = "\n".join(
        f"- {r['provider'].title()}: {_fmt_time(r['elapsed_s'])}, "
        f"{len(r.get('final_answer',''))} chars, "
        f"{len(r.get('active_agents',[]))} agents, "
        f"{len(r.get('errors',[]))} errors"
        for r in results if not r.get("error")
    )
    prompt = (
        "Based on a side-by-side political planning tool comparison (OpenAI gpt-4o, "
        "Anthropic claude-sonnet-4-5, Gemini gemini-2.5-flash), write a Recommendations "
        "section (200–250 words) structured as three short paragraphs:\n"
        "1. **Best for staff training / learning:** which provider and why.\n"
        "2. **Best for live campaign use:** which provider and why.\n"
        "3. **Best for rapid prototyping / iteration:** which provider and why.\n\n"
        "End with one sentence naming the overall winner for political plan generation.\n\n"
        f"Run data:\n{run_summary}\n\n"
        "No header. Write directly."
    )
    return [_llm_analyze(prompt), ""]


def _build_changeagent_section(
    ca_result: dict,
    results: list[dict],
    district: dict,
) -> list[str]:
    lines: list[str] = []

    if not CHANGEAGENT_API_KEY:
        lines += [
            "ChangeAgent integration pending API access — this section will populate "
            "automatically when `CHANGEAGENT_API_KEY` is set in the environment.",
            "",
            "_Request access at [changeagent.com](https://changeagent.com)._",
        ]
        return lines

    lines += [
        f"**Endpoint:** `{ca_result['url']}`  ",
        f"**District:** {district['label']}  ",
        "",
    ]

    if ca_result.get("error"):
        lines += [
            f"**API call failed:** `{ca_result['error']}`",
            "",
            "Benchmark comparison will populate automatically when the API returns a "
            "successful response.",
        ]
        return lines

    data = ca_result.get("data") or {}
    lines += [
        "**ChangeAgent Program Benchmarks (raw response):**",
        "",
        "```json",
        json.dumps(data, indent=2),
        "```",
        "",
        "**Comparison Against Powerbuilder Calculations:**",
        "",
    ]

    # Pull Powerbuilder contact goals from the first successful finance entry
    pb_contacts: dict[str, str] = {}
    for r in results:
        fe = _find_entry(r["structured_data"], "cost_calculator")
        if not fe:
            fe = _find_entry(r["structured_data"], "finance")
        if fe:
            budget = fe.get("budget_available") or fe.get("total_cost")
            bp = fe.get("budget_program") or {}
            pb_contacts = {
                "mail_contacts":   _fmt_num(bp.get("mail_piece", {}).get("contacts")),
                "phone_contacts":  _fmt_num(bp.get("phone_call", {}).get("contacts")),
                "canvass_contacts":_fmt_num(bp.get("canvassing", {}).get("contacts")),
                "digital_contacts":_fmt_num(bp.get("digital", {}).get("contacts")),
                "total_budget":    _fmt_num(budget),
            }
            break

    ca_canvass  = (data.get("canvassing") or {}).get("doors_per_day_benchmark", "N/A")
    ca_vol_rate = (data.get("volunteer_recruitment") or {}).get("rate_benchmark", "N/A")
    ca_phone    = (data.get("phone_banking") or {}).get("contacts_per_hour_benchmark", "N/A")

    lines += [
        "| Metric | ChangeAgent Benchmark | Powerbuilder Calculated |",
        "|--------|----------------------|------------------------|",
        f"| Canvassing doors/day | {ca_canvass} | "
        f"{pb_contacts.get('canvass_contacts', 'see Budget section')} |",
        f"| Volunteer recruitment rate | {ca_vol_rate} | *(program-level, see Budget section)* |",
        f"| Phone contacts/hour | {ca_phone} | "
        f"{pb_contacts.get('phone_contacts', 'see Budget section')} |",
        f"| Mail pieces (total) | *(not in benchmarks API)* | "
        f"{pb_contacts.get('mail_contacts', 'see Budget section')} |",
        f"| Total budget modeled | *(not in benchmarks API)* | "
        f"{pb_contacts.get('total_budget', 'see Budget section')} |",
        "",
        "_Full integration available when ChangeAgent API returns complete district "
        "program analytics._",
    ]
    return lines


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    ts       = datetime.now().strftime("%Y%m%d_%H%M%S")
    date_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    print(f"\n{'='*62}")
    print("  Powerbuilder LLM White Paper Comparison")
    print(f"{'='*62}")
    print(f"  Query:     {QUERY[:70]}...")
    print(f"  Primary:   {PRIMARY_DISTRICT['label']}")
    print(f"  Fallback:  {FALLBACK_DISTRICT['label']}")
    print(f"  Providers: {', '.join(p.title() for p in PROVIDERS)}")
    print(f"  ChangeAgent: {'key present' if CHANGEAGENT_API_KEY else 'key absent (section 8 will be placeholder)'}")
    print(f"{'='*62}\n")

    # -------------------------------------------------------------------
    # 1. Run each provider sequentially
    # -------------------------------------------------------------------
    print("Running providers (sequential to avoid env conflicts):")
    results: list[dict] = []
    for provider in PROVIDERS:
        r = run_provider(provider)
        results.append(r)

        # Save raw final_answer for manual side-by-side review
        raw_path = EXPORTS_DIR / f"white_paper_{provider}_{ts}.md"
        with open(raw_path, "w", encoding="utf-8") as fh:
            fh.write(f"# {provider.title()} — Raw Output\n\n")
            fh.write(f"**Query:** {QUERY}\n\n")
            fh.write(f"**Wall-clock time:** {_fmt_time(r['elapsed_s'])}\n\n")
            fh.write(f"**Active agents:** {', '.join(r['active_agents'])}\n\n")
            if r.get("error"):
                fh.write(f"**Fatal error:** {r['error']}\n\n")
            if r.get("errors"):
                fh.write("**Non-fatal errors:**\n")
                for e in r["errors"]:
                    fh.write(f"  - {e}\n")
                fh.write("\n")
            fh.write("---\n\n")
            fh.write(r["final_answer"] or "*(no output)*")
        print(f"    Saved: exports/white_paper_{provider}_{ts}.md")

    # Determine which district was actually used
    district_used = PRIMARY_DISTRICT
    for r in results:
        if _has_coverage_note(r["structured_data"]):
            district_used = FALLBACK_DISTRICT
            print(
                f"\n  Note: AZ-06 crosswalk unavailable — "
                f"pipeline resolved to {FALLBACK_DISTRICT['label']}"
            )
            break

    # -------------------------------------------------------------------
    # 2. ChangeAgent API call
    # -------------------------------------------------------------------
    print(f"\nQuerying ChangeAgent API...", end="", flush=True)
    if CHANGEAGENT_API_KEY:
        ca_result = _call_changeagent(
            district_used["state_fips"], district_used["district_id"]
        )
        if ca_result["error"]:
            print(f" failed ({ca_result['error'][:60]})")
        else:
            print(" ok")
    else:
        ca_result = {"url": CHANGEAGENT_URL, "data": None, "error": None}
        print(" skipped (CHANGEAGENT_API_KEY not set)")

    # -------------------------------------------------------------------
    # 3. Build white paper
    # -------------------------------------------------------------------
    print("\nGenerating white paper (LLM synthesis in progress)...")

    lines: list[str] = [
        "# Powerbuilder LLM Provider White Paper",
        "",
        f"**Generated:** {date_str}  ",
        f"**Query:** *{QUERY}*  ",
        f"**District used:** {district_used['label']}  ",
        f"**Providers:** {', '.join(p.title() for p in PROVIDERS)}  ",
        "",
        "---",
        "",
    ]

    # Executive Summary
    print("  Executive Summary...")
    lines += [
        "## Executive Summary", "",
        _build_executive_summary(results, district_used),
        "", "---", "",
    ]

    # Methodology
    print("  Methodology...")
    from chat.utils.llm_config import PINECONE_INDEX_NAMES, get_provider_info
    lines += [
        "## Methodology", "",
        f"**Date run:** {date_str}  ",
        f"**Query:** *{QUERY}*  ",
        f"**District:** {district_used['label']}  ",
        f"**COMPARISON_MODE:** False (all providers share OpenAI production embedding "
        f"and index for retrieval consistency; LLM generation switches per provider)  ",
        "",
        "| Provider | Completion Model | Pinecone Index | Run Time | Status |",
        "|----------|-----------------|----------------|----------|--------|",
    ]
    for r in results:
        p = r["provider"]
        info = get_provider_info(p)
        index = PINECONE_INDEX_NAMES.get(p, "powerbuilder-openai")
        status = f"OK" if not r.get("error") else f"FAILED"
        lines.append(
            f"| {p.title()} | `{info['model']}` | `{index}` | "
            f"{_fmt_time(r['elapsed_s'])} | {status} |"
        )
    lines += ["", "---", ""]

    # Section 1: Research Retrieval
    print("  Section 1: Research Retrieval...")
    lines += ["## Section 1: Research Retrieval", ""]
    lines += _build_research_retrieval(results)
    lines += ["---", ""]

    # Section 2: Win Number
    print("  Section 2: Win Number Accuracy...")
    lines += ["## Section 2: Win Number Accuracy", ""]
    lines += _build_win_number(results)
    lines += ["", "---", ""]

    # Section 3: Precinct Targeting
    print("  Section 3: Precinct Targeting...")
    lines += ["## Section 3: Precinct Targeting", ""]
    lines += _build_precinct_targeting(results)
    lines += ["---", ""]

    # Section 4: Messaging Quality
    print("  Section 4: Messaging Quality...")
    lines += ["## Section 4: Messaging Quality", ""]
    lines += _build_messaging_quality(results)
    lines += ["---", ""]

    # Section 5: Speculation Behavior
    print("  Section 5: Speculation Behavior...")
    lines += ["## Section 5: Speculation Behavior", ""]
    lines += _build_speculation_behavior(results)
    lines += ["---", ""]

    # Section 6: Output Quality Scorecard
    print("  Section 6: Output Quality Scorecard...")
    lines += ["## Section 6: Output Quality Scorecard", ""]
    lines += _build_scorecard(results)
    lines += ["---", ""]

    # Section 7: Recommendations
    print("  Section 7: Recommendations...")
    lines += ["## Section 7: Recommendations", ""]
    lines += _build_recommendations(results)
    lines += ["---", ""]

    # Section 8: ChangeAgent Field Benchmarks
    print("  Section 8: ChangeAgent Field Benchmarks...")
    lines += ["## Section 8: ChangeAgent Field Benchmarks", ""]
    lines += _build_changeagent_section(ca_result, results, district_used)
    lines += ["", "---", ""]

    # Appendix: Pipeline run stats
    lines += [
        "## Appendix: Pipeline Run Statistics",
        "",
        "| Provider | Wall Clock | Agents Run | Non-fatal Errors | Answer Length |",
        "|----------|------------|------------|-----------------|---------------|",
    ]
    for r in results:
        agents_str = ", ".join(r.get("active_agents", [])) or "none"
        lines.append(
            f"| {r['provider'].title()} | {_fmt_time(r['elapsed_s'])} | "
            f"{agents_str[:50]} | {len(r.get('errors', []))} | "
            f"{len(r.get('final_answer', ''))} chars |"
        )

    lines += ["", "### Non-fatal Pipeline Errors", ""]
    for r in results:
        if r.get("errors"):
            lines.append(f"**{r['provider'].title()}:**")
            for e in r["errors"][:10]:
                lines.append(f"  - {e}")
            lines.append("")

    # -------------------------------------------------------------------
    # 4. Write white paper
    # -------------------------------------------------------------------
    wp_path = EXPORTS_DIR / f"llm_white_paper_{ts}.md"
    with open(wp_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))

    print(f"\n{'='*62}")
    print(f"  White paper:   exports/llm_white_paper_{ts}.md")
    print(f"  Raw outputs:")
    for provider in PROVIDERS:
        print(f"    exports/white_paper_{provider}_{ts}.md")
    print(f"{'='*62}\n")


if __name__ == "__main__":
    main()
