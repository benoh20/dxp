# powerbuilder/chat/agents/messaging.py
"""
Field Organizer agent. Generates targeted campaign messaging — canvassing scripts,
text scripts, mail narratives, and digital copy — grounded exclusively in research
findings from researcher.py and precinct demographic data from precincts.py.

The LLM is explicitly constrained: every claim must be traceable to a finding in
research_results. It does not invent statistics, polling numbers, or talking points.

Outputs are appended to research_results as formatted Markdown strings so the
synthesizer can incorporate them directly into the final deliverable.
"""

import json
import logging
import os
import re
from datetime import datetime
from typing import Optional

from dotenv import load_dotenv
load_dotenv()

from ..utils.llm_config import get_completion_client

from .state import AgentState

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

# Exemplar templates live in powerbuilder/tool_templates/. When a file exists,
# the LLM uses it as a structural guide for that format (voice, section order,
# approximate length). Drop .md files into this folder to customise output
# format without touching code. Falls back to FORMAT_DESCRIPTIONS if absent.
TEMPLATES_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "../../tool_templates")
)

# Maps format key → template filename in tool_templates/.
# None means no template exists; falls back to FORMAT_DESCRIPTIONS.
TEMPLATE_FILES = {
    "canvassing_script": "canvass_script_template.md",
    "phone_script":      "phone_script_template.md",
    "text_script":       "text_script_template.md",
    "mail_narrative":    None,
    "digital_copy":      "digital_copy_template.md",
}

# Default structural descriptions used when no template file exists.
FORMAT_DESCRIPTIONS = {
    "canvassing_script": (
        "A door-to-door canvassing script with:\n"
        "- Opening introduction (2-3 sentences)\n"
        "- 2-3 key talking points tied to specific research findings\n"
        "- Responses to 1-2 likely voter objections\n"
        "- A closing ask or call to action\n"
        "- Estimated conversation time: 3-5 minutes"
    ),
    "phone_script": (
        "A phone banking script with:\n"
        "- A brief introduction identifying the caller and campaign (2 sentences)\n"
        "- A pivot to 1-2 key issues from research, framed as a question\n"
        "- A support-level question (1-5 scale)\n"
        "- Tailored responses for strong supporters, undecideds, and opposers\n"
        "- A closing ask to commit to voting\n"
        "- Estimated call time: 2-4 minutes"
    ),
    "text_script": (
        "3 SMS text message templates, each under 160 characters, "
        "with a clear call to action. Use [NAME] as a personalisation placeholder. "
        "Include an opt-out instruction on first contact."
    ),
    "mail_narrative": (
        "A 200-300 word direct mail narrative written in second person. "
        "Highlight 2-3 issues most relevant to the demographic profile. "
        "End with a specific, concrete call to action."
    ),
    "digital_copy": (
        "4 digital ad copy variations (Variation A through D), "
        "each under 30 words, suitable for Facebook, Instagram, and display ads."
    ),
}

# Section markers used to split the LLM's single response into five strings.
# The LLM is explicitly instructed to preserve these exactly.
SECTION_MARKERS = {
    "canvassing_script": "===CANVASSING_SCRIPT===",
    "phone_script":      "===PHONE_SCRIPT===",
    "text_script":       "===TEXT_SCRIPT===",
    "mail_narrative":    "===MAIL_NARRATIVE===",
    "digital_copy":      "===DIGITAL_COPY===",
}

# Human-readable labels for the research_results header of each output
FORMAT_LABELS = {
    "canvassing_script": "CANVASSING SCRIPT",
    "phone_script":      "PHONE BANKING SCRIPT",
    "text_script":       "TEXT SCRIPT (SMS)",
    "mail_narrative":    "MAIL NARRATIVE",
    "digital_copy":      "DIGITAL COPY BLOCK",
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_costs() -> dict:
    """
    Load per-contact cost rates from tool_templates/costs.json.
    Returns an empty dict if the file is missing so callers degrade gracefully.
    """
    path = os.path.join(TEMPLATES_DIR, "costs.json")
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _format_costs_context(costs: dict) -> str:
    """
    Build a compact cost-context block for the LLM prompt so scripts can
    include realistic field goals without inventing numbers.
    """
    if not costs:
        return ""
    lines = ["CAMPAIGN COST RATES (for context only — do not include in scripts unless relevant):"]
    mapping = {
        "canvassing": ("Door knock", "cost_per_door",     "doors_per_hour"),
        "phones":     ("Phone call", "cost_per_contact",  None),
        "text":       ("Text",       "cost_per_text",      None),
        "mail":       ("Mail piece", "cost_per_piece",     None),
        "digital":    ("Digital",    "cost_per_impression", None),
    }
    for key, (label, cost_key, rate_key) in mapping.items():
        section = costs.get(key, {})
        cost = section.get(cost_key)
        if cost is not None:
            rate_note = f", {section[rate_key]} per hour avg" if rate_key and section.get(rate_key) else ""
            lines.append(f"  - {label}: ${cost:.2f}{rate_note}")
    return "\n".join(lines)


def _load_template(format_name: str) -> Optional[str]:
    """
    Load an exemplar template from tool_templates/ if it exists.
    Returns None if the file is missing so the caller falls back to
    FORMAT_DESCRIPTIONS. No error is raised — missing templates are expected
    until the user populates the tool_templates/ folder.
    """
    filename = TEMPLATE_FILES.get(format_name)
    if not filename:
        return None
    path = os.path.join(TEMPLATES_DIR, filename)
    try:
        with open(path) as f:
            content = f.read().strip()
        logger.debug(f"Loaded template: {path}")
        return content
    except FileNotFoundError:
        return None


def _get_format_instruction(format_name: str) -> str:
    """
    Returns the exemplar template if one exists in tool_templates/, otherwise
    returns the built-in structural description. This is what goes into the
    LLM prompt to guide structure for each format.
    """
    template = _load_template(format_name)
    if template:
        return (
            f"Use the following exemplar as a structural guide "
            f"(fill it with content drawn ONLY from the research above):\n\n{template}"
        )
    return FORMAT_DESCRIPTIONS[format_name]


def _parse_date_str(date_val) -> Optional[datetime]:
    """
    Parse a date string into a datetime for recency comparisons.
    Mirrors the logic in researcher.py — move both to chat/config.py
    when a shared utilities module is created.
    """
    if not date_val or str(date_val).strip().lower() in ("date unknown", "unknown", ""):
        return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y", "%B %Y", "%b %Y", "%B %d, %Y", "%Y"):
        try:
            return datetime.strptime(str(date_val).strip(), fmt)
        except ValueError:
            continue
    return None


def _extract_most_recent_date(research_results: list) -> str:
    """
    Scan research_results memo headers for the DATE field written by
    researcher.py (format: --- MEMO FROM SOURCE: ... | DATE: {date} ---) and
    return the most recent date string found. Returns "unknown" if none parse.
    """
    dated = []
    for memo in research_results:
        match = re.search(r"\| DATE: ([^|\-\n]+?) ---", memo)
        if match:
            raw = match.group(1).strip()
            parsed = _parse_date_str(raw)
            if parsed:
                dated.append((parsed, raw))
    if dated:
        dated.sort(key=lambda x: x[0], reverse=True)
        return dated[0][1]
    return "unknown"


def _summarize_demographics(precincts: list) -> str:
    """
    Build a concise demographic summary from the precincts structured_data entry
    for use in the LLM prompt. Computes totals and percentages across all
    target precincts, using total_cvap (or total_population) as the universe.
    """
    if not precincts:
        return "No precinct demographic data available."

    exclude = {"precinct_geoid", "precinct_name", "approximate_boundary"}
    metric_keys = [k for k in precincts[0].keys() if k not in exclude]

    totals: dict = {k: 0.0 for k in metric_keys}
    approx_count = 0

    for p in precincts:
        for k in metric_keys:
            try:
                totals[k] += float(p.get(k) or 0)
            except (ValueError, TypeError):
                pass
        if p.get("approximate_boundary"):
            approx_count += 1

    universe = totals.get("total_cvap") or totals.get("total_population") or 0

    lines = [f"Target precincts: {len(precincts)}"]
    for k, v in totals.items():
        if k in ("total_cvap", "total_population"):
            lines.append(f"  {k}: {int(v):,}")
        elif universe > 0:
            lines.append(f"  {k}: {int(v):,} ({v / universe * 100:.1f}% of universe)")
        else:
            lines.append(f"  {k}: {int(v):,}")

    if approx_count:
        lines.append(
            f"  Note: {approx_count}/{len(precincts)} precincts use approximated boundaries."
        )

    return "\n".join(lines)


def _parse_sections(raw: str) -> dict:
    """
    Split the LLM response on SECTION_MARKERS into a dict of {format: content}.
    Gracefully degrades: if no markers are found, returns the full raw text
    under 'canvassing_script' rather than discarding the output entirely.
    """
    result = {}
    marker_list = list(SECTION_MARKERS.items())  # preserves insertion order

    for i, (key, marker) in enumerate(marker_list):
        start = raw.find(marker)
        if start == -1:
            continue
        content_start = start + len(marker)
        # Content ends at the next marker, or at end of string
        end = len(raw)
        for _, next_marker in marker_list[i + 1:]:
            next_pos = raw.find(next_marker)
            if next_pos != -1:
                end = next_pos
                break
        result[key] = raw[content_start:end].strip()

    if not result:
        logger.warning(
            "MessagingAgent: Section markers not found in LLM response. "
            "Returning full output under 'canvassing_script'."
        )
        result["canvassing_script"] = raw.strip()

    return result


# ---------------------------------------------------------------------------
# Node
# ---------------------------------------------------------------------------

def messaging_node(state: AgentState) -> dict:
    """
    Field Organizer agent. Reads the whiteboard and generates five messaging
    formats grounded exclusively in the research findings already collected:
    canvassing script, phone script, text templates, mail narrative, digital copy.

    Reads from state:
      - structured_data: expects a precincts entry with demographic data
      - research_results: expects memo strings from researcher.py

    Writes to state:
      - research_results: five formatted Markdown messaging outputs (appended)
      - active_agents:    ["messaging"] (appended)
    """
    research_results = state.get("research_results", [])
    structured_data  = state.get("structured_data", [])

    # -----------------------------------------------------------------------
    # 1. Read precinct demographic context from the whiteboard
    # -----------------------------------------------------------------------
    precincts_entry = next(
        (d for d in structured_data if d.get("agent") == "precincts"), None
    )
    precincts     = precincts_entry.get("precincts", [])  if precincts_entry else []
    district_id   = (precincts_entry or {}).get("district_id",   "unknown")
    district_type = (precincts_entry or {}).get("district_type", "unknown")

    district_label = (
        f"{district_type.replace('_', ' ').title()} {district_id}"
        if district_id != "unknown"
        else "target district"
    )

    if not precincts:
        logger.warning(
            "MessagingAgent: No precinct data found in structured_data. "
            "Messaging will proceed without demographic targeting — run precincts first."
        )

    if not research_results:
        return {
            "errors":        ["MessagingAgent: No research findings in state. Run researcher first."],
            "active_agents": ["messaging"],
        }

    # -----------------------------------------------------------------------
    # 2. Build prompt inputs
    # -----------------------------------------------------------------------
    demographic_summary   = _summarize_demographics(precincts)
    most_recent_date      = _extract_most_recent_date(research_results)
    research_context      = "\n\n".join(research_results)
    costs_context         = _format_costs_context(_load_costs())

    canvassing_instruction = _get_format_instruction("canvassing_script")
    phone_instruction      = _get_format_instruction("phone_script")
    text_instruction       = _get_format_instruction("text_script")
    mail_instruction       = _get_format_instruction("mail_narrative")
    digital_instruction    = _get_format_instruction("digital_copy")

    # -----------------------------------------------------------------------
    # 3. Single LLM call — all five formats, separated by section markers
    # -----------------------------------------------------------------------
    llm = get_completion_client(temperature=0.4)  # modest creativity for copywriting

    prompt = f"""You are an expert field organizer and political messaging strategist.
Generate targeted campaign messaging materials for the {district_label}.

━━━ HARD CONSTRAINT — READ CAREFULLY ━━━
You must draw ALL content EXCLUSIVELY from the RESEARCH FINDINGS section below.
Do NOT invent statistics, polling numbers, quotes, or claims not present there.
Do NOT reference issues, demographics, or events not mentioned in the research.
If the research does not support a talking point, omit it entirely.
Every claim in your output must be directly traceable to a provided finding.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

DEMOGRAPHIC PROFILE OF TARGET PRECINCTS:
{demographic_summary}

{costs_context}

RESEARCH FINDINGS (your only permitted source of messaging content):
{research_context}

━━━ OUTPUT INSTRUCTIONS ━━━
Generate all five sections below. Each section must:
1. Be grounded exclusively in the research findings above.
2. Be tailored to the demographic profile of the target precincts.
3. Close with this exact recency note in italics:
   *Research sourced from materials dated as recently as {most_recent_date}.*

You MUST include each section marker exactly as shown on its own line.
Do not rename, reorder, or omit any marker.

{SECTION_MARKERS["canvassing_script"]}
{canvassing_instruction}

{SECTION_MARKERS["phone_script"]}
{phone_instruction}

{SECTION_MARKERS["text_script"]}
{text_instruction}

{SECTION_MARKERS["mail_narrative"]}
{mail_instruction}

{SECTION_MARKERS["digital_copy"]}
{digital_instruction}
"""

    try:
        raw_response = llm.invoke(prompt).content
    except Exception as e:
        return {
            "errors":        [f"MessagingAgent: LLM call failed — {e}"],
            "active_agents": ["messaging"],
        }

    # -----------------------------------------------------------------------
    # 4. Parse into five separate Markdown strings and append to whiteboard
    # -----------------------------------------------------------------------
    sections = _parse_sections(raw_response)

    formatted_outputs = []
    for key, label in FORMAT_LABELS.items():
        content = sections.get(key)
        if content:
            formatted_outputs.append(
                f"--- MESSAGING OUTPUT: {label} | DISTRICT: {district_label} "
                f"| RESEARCH DATE: {most_recent_date} ---\n{content}\n"
            )

    if not formatted_outputs:
        return {
            "errors":        ["MessagingAgent: LLM returned no parseable content."],
            "active_agents": ["messaging"],
        }

    logger.info(
        f"MessagingAgent: Generated {len(formatted_outputs)}/5 messaging formats "
        f"for {district_label} using research dated as recently as {most_recent_date}."
    )

    return {
        "research_results": formatted_outputs,
        "active_agents":    ["messaging"],
    }
