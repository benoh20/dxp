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
    # Milestone H: platform-specific social media variants. Templates are
    # optional; falling back to FORMAT_DESCRIPTIONS gives sensible defaults.
    "meta_post":         None,
    "youtube_script":    None,
    "tiktok_script":     None,
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
    # ---- Milestone H: research-backed platform-shaped social variants ----
    # Each variant maps to a specific finding in the literature. See the
    # 'Research basis' section of the README for the full citation list.
    "meta_post": (
        "A Facebook/Instagram MOBILIZATION post (Wesleyan Media Project 2024 "
        "shows Meta is overwhelmingly used for action and GOTV, not persuasion). "
        "Format:\n"
        "- 1-line scroll-stopping headline (under 90 characters)\n"
        "- 2 to 3 sentence body, kitchen-table economic frame where possible "
        "  (TFC 2024: abortion-only mobilization framing was 1.8x to 5x more "
        "  expensive per conversion than top creative)\n"
        "- Single concrete CTA using identity-as-noun framing where it fits "
        "  ('be a voter', 'join the X for Y', not 'vote', 'help us'); see "
        "  Bryan, Walton, Rogers and Dweck, PNAS 2011\n"
        "- One link placeholder: [LINK]\n"
        "Total length under 280 characters in the post body."
    ),
    "youtube_script": (
        "A YouTube PERSUASION script, 60 to 90 seconds spoken (Wesleyan 2024: "
        "YouTube carried more issue and persuasion content than Meta and was "
        "closer to traditional TV in function). Format:\n"
        "- [0:00 to 0:05] HOOK: a question or contrast that names the stake "
        "  for this voter\n"
        "- [0:05 to 0:30] EVIDENCE: 2 to 3 specific findings from the research "
        "  above with attribution\n"
        "- [0:30 to 0:55] CONTRAST or STORY: a brief grounded comparison or "
        "  one short voter story rendered in plain language\n"
        "- [0:55 to 1:30] ASK: action specific to this district, with a date "
        "  if available\n"
        "Include speaker direction in [brackets] sparingly."
    ),
    "tiktok_script": (
        "A TikTok or Reels ATTENTION script, 15 to 30 seconds (Chmel, Kim, "
        "Marshall and Lubin 2024: lifestyle-wrapped political content from "
        "creators outperformed traditional outreach; politainment frame works "
        "better than overtly political delivery for under-35 audiences). "
        "Format:\n"
        "- [HOOK 0 to 1.5s] open with a curiosity gap or strong visual cue, "
        "  no party logos\n"
        "- [PAYOFF 1.5 to 20s] one specific finding from the research, "
        "  delivered in conversational first-person\n"
        "- [TURN 20 to 28s] reframe to the viewer's stake (their district, "
        "  their cohort, their cost-of-living)\n"
        "- [CTA 28 to 30s] end on a question or a low-friction ask (follow, "
        "  share, check registration); avoid imperative 'vote for X' phrasing\n"
        "Caption: under 150 characters, 2 to 4 hashtags max, no party tags."
    ),
}

# Maps ISO 639-1 language codes to a (display_name, native_call_to_arms) pair.
# ---------------------------------------------------------------------------
# Milestone L: mobilization vs. persuasion mode
#
# Wesleyan Media Project 2024 (https://mediaproject.wesleyan.edu/2024-summary-062425/)
# documents that mobilization and persuasion are fundamentally different
# strategic functions in modern campaigns: mobilization turns out existing
# supporters, persuasion moves undecided voters. Tech for Campaigns 2024
# (https://www.techforcampaigns.org/results/2024-digital-ads-report) found
# mobilization-themed creative cost 1.8-5x less per outcome than persuasion-
# themed creative on the same platforms. The mode toggle lets a user pick
# the strategic frame explicitly so all eight messaging formats are shaped
# coherently, instead of the LLM hedging across both at once.
#
# "auto" means no override — the manager's existing intent detection runs
# and the prompts are unchanged from pre-Milestone-L behavior.
# ---------------------------------------------------------------------------

PLAN_MODES = ("auto", "mobilization", "persuasion")

MODE_LABELS = {
    "auto":         "Auto",
    "mobilization": "Mobilization",
    "persuasion":   "Persuasion",
}

MODE_DESCRIPTIONS = {
    "mobilization": (
        "MOBILIZATION MODE: Audience is supporters who already agree with our position. "
        "The job is to make voting feel inevitable, social, and urgent. Use ID-as-noun "
        "framing ('be a voter') over ID-as-verb ('go vote') per Bryan/Walton/Rogers/Dweck "
        "PNAS 2011. Lead with deadlines, polling locations, and peer-visible action. "
        "Avoid persuasive argumentation; the audience is already with us. Cheaper per "
        "outcome at scale per Tech for Campaigns 2024."
    ),
    "persuasion": (
        "PERSUASION MODE: Audience is undecided or soft-opposing voters who can be moved. "
        "The job is to introduce evidence, address objections, and reframe the choice. "
        "Allow longer copy, contrast structure (problem -> evidence -> contrast -> ask), "
        "and named issues from the research findings. Effect sizes are small in absolute "
        "terms (Coppock/Hill/Vavreck APSR 2024) but log-scaling with model size "
        "(Hackenburg et al. PNAS 2025), so write tight, specific, falsifiable copy."
    ),
    "auto": (
        "AUTO MODE: No mode override from the user. Use the natural mix of mobilization "
        "and persuasion appropriate to the research findings and demographic profile."
    ),
}

# Per-format CTA shape hint, applied on top of MODE_DESCRIPTIONS. The hint is
# format-specific because the same mode wants a different verb structure on a
# door knock vs a TikTok script.
MODE_CTA_HINTS = {
    "mobilization": {
        "canvassing_script": "Close on a same-day or near-future commitment ('Can I count on you to vote on November 5th?').",
        "phone_script":      "Confirm polling location and a specific time the supporter will go.",
        "text_script":       "Single clear ask: vote, plan, or check registration. No persuasion text.",
        "mail_narrative":    "Lead with deadlines and the recipient's polling location. End on a peer-visible action ('join your neighbors').",
        "digital_copy":      "Headline names a deadline. Body under 280 chars. CTA verb is 'Vote', 'RSVP', 'Pledge'.",
        "meta_post":         "ID-as-noun construction. Kitchen-table economic anchor. Body under 280 chars.",
        "youtube_script":    "60-90s. Hook at 0:00 names the deadline or polling moment. End on peer-visible commitment.",
        "tiktok_script":     "15-30s. Open on the action, not the issue. End on a question that invites duet ('Are you in?').",
    },
    "persuasion": {
        "canvassing_script": "Use deep-canvass structure: ask the voter what matters to them, listen, then connect to research-backed evidence.",
        "phone_script":      "Allow longer dialogue. Surface one named contrast point from the research findings.",
        "text_script":       "Two-message exchange: open with a question, follow up with evidence after a reply.",
        "mail_narrative":    "Long-form contrast structure. Lead with a named issue from research, then evidence, then ask.",
        "digital_copy":      "Headline poses the contrast. Body cites one piece of research-grounded evidence.",
        "meta_post":         "Lead with the contrast frame, not the deadline. Body up to 600 chars allowed.",
        "youtube_script":    "60-90s with explicit timestamp markers (0:00 hook, 0:05 evidence, 0:30 contrast, 0:55 ask).",
        "tiktok_script":     "15-30s. Open on the surprising claim, end on the source. Lifestyle-wrapped, no party logos.",
    },
    "auto": {},  # no per-format override
}


def _normalize_plan_mode(value):
    """Defensive normalization: accept None, unknown strings, mixed case, etc."""
    if not isinstance(value, str):
        return "auto"
    v = value.strip().lower()
    if v not in PLAN_MODES:
        return "auto"
    return v


def _build_mode_directive(plan_mode: str) -> str:
    """
    Construct the strategic-frame directive that goes near the top of the
    messaging prompt, just below the language directive and just above the
    HARD CONSTRAINT block. Returns an empty string for 'auto' so the prompt
    is identical to pre-Milestone-L behavior in that case.
    """
    plan_mode = _normalize_plan_mode(plan_mode)
    if plan_mode == "auto":
        return ""
    description = MODE_DESCRIPTIONS[plan_mode]
    return (
        f"\u2501\u2501\u2501 STRATEGIC FRAME \u2501\u2501\u2501\n"
        f"{description}\n"
        f"Apply this frame consistently across all eight messaging sections; do not hedge.\n"
        f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n\n"
    )


def _build_mode_cta_block(plan_mode: str) -> str:
    """
    Construct the per-format CTA hints block. Empty string for 'auto'.
    """
    plan_mode = _normalize_plan_mode(plan_mode)
    if plan_mode == "auto":
        return ""
    hints = MODE_CTA_HINTS.get(plan_mode, {})
    if not hints:
        return ""
    label = MODE_LABELS[plan_mode].upper()
    lines = [f"PER-FORMAT CTA SHAPE ({label}):"]
    for fmt_key, hint in hints.items():
        lines.append(f"  - {fmt_key}: {hint}")
    return "\n".join(lines) + "\n\n"


# Used to construct the language directive at the top of the prompt and the
# label in the output header. Add new languages here — messaging.py is the
# only place a translator-style instruction is needed.
LANGUAGE_LABELS: dict[str, tuple[str, str]] = {
    "en": ("English",    ""),
    "es": ("Spanish",    " Use warm, respectful t\u00fa-form address (not formal usted) for door knocks; "
                         "use usted for phone scripts and mail to elders. Prefer plain conversational "
                         "Spanish over translated political jargon."),
    "zh": ("Mandarin Chinese", " Use Simplified Chinese characters. Prefer respectful, plain phrasing "
                               "over Anglicisms or transliterations."),
    "vi": ("Vietnamese", " Use respectful Vietnamese forms appropriate to the audience age cohort."),
    "ko": ("Korean",     " Use \ud574\uc694-style polite form for door knocks; \ud569\uc2dc\ub2e4-style formal form for mail."),
}

# Section markers used to split the LLM's single response into five strings.
# The LLM is explicitly instructed to preserve these exactly.
SECTION_MARKERS = {
    "canvassing_script": "===CANVASSING_SCRIPT===",
    "phone_script":      "===PHONE_SCRIPT===",
    "text_script":       "===TEXT_SCRIPT===",
    "mail_narrative":    "===MAIL_NARRATIVE===",
    "digital_copy":      "===DIGITAL_COPY===",
    # Milestone H: social platform variants
    "meta_post":         "===META_POST===",
    "youtube_script":    "===YOUTUBE_SCRIPT===",
    "tiktok_script":     "===TIKTOK_SCRIPT===",
}

# Human-readable labels for the research_results header of each output
FORMAT_LABELS = {
    "canvassing_script": "CANVASSING SCRIPT",
    "phone_script":      "PHONE BANKING SCRIPT",
    "text_script":       "TEXT SCRIPT (SMS)",
    "mail_narrative":    "MAIL NARRATIVE",
    "digital_copy":      "DIGITAL COPY BLOCK",
    # Milestone H: social platform variants
    "meta_post":         "META POST (Mobilization)",
    "youtube_script":    "YOUTUBE SCRIPT (Persuasion)",
    "tiktok_script":     "TIKTOK SCRIPT (Attention)",
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


# ---------------------------------------------------------------------------
# Milestone H: format checker for the social variants
# ---------------------------------------------------------------------------

# Approximate length budgets per platform (chars). These are deliberately
# generous and are warnings, not hard rejections — the LLM occasionally needs
# breathing room for non-English variants which run longer.
SOCIAL_LENGTH_LIMITS: dict[str, int] = {
    "meta_post":      900,    # body + CTA + 1 line + a little slack
    "youtube_script": 2200,   # ~90 seconds of conversational copy plus stage directions
    "tiktok_script":  900,    # 30-second script plus caption block
}

# Phrases that suggest the script does NOT open with a hook. We're checking
# the FIRST 60 characters of the script body (skipping any leading bracket
# direction like '[0:00 to 0:05]').
_FLAT_OPENERS: tuple[str, ...] = (
    "hello", "hi there", "hi everyone", "my name is", "i'm a", "i am a",
    "in this video", "today we", "this video", "welcome to", "thanks for",
)


def _strip_leading_direction(text: str) -> str:
    """Drop a leading [bracketed direction] and any whitespace so the hook check
    looks at actual spoken/visible copy, not stage cues."""
    stripped = text.lstrip()
    if stripped.startswith("["):
        close = stripped.find("]")
        if close != -1:
            stripped = stripped[close + 1 :].lstrip()
    return stripped


def check_social_format(sections: dict) -> dict[str, list[str]]:
    """
    Inspect the parsed social sections and return a dict of
    {format_key: [warning, ...]} for any variant that drifts from format.

    Checks:
      - length: warns if the section is materially longer than the platform
        budget (TikTok scripts that run 4 paragraphs, etc.)
      - hook: warns if a TikTok or YouTube script opens with a flat 'hello,
        my name is' style intro instead of a curiosity hook

    Empty or missing sections are silently skipped — the caller already
    handles the 'LLM returned no parseable content' case.
    """
    warnings: dict[str, list[str]] = {}
    for key, limit in SOCIAL_LENGTH_LIMITS.items():
        content = (sections.get(key) or "").strip()
        if not content:
            continue
        section_warnings: list[str] = []

        if len(content) > limit:
            section_warnings.append(
                f"runs {len(content)} chars, target under {limit}"
            )

        if key in ("tiktok_script", "youtube_script"):
            opener = _strip_leading_direction(content)[:60].lower()
            if any(opener.startswith(flat) for flat in _FLAT_OPENERS):
                section_warnings.append(
                    "opens with a flat intro (consider a curiosity hook in the first beat)"
                )

        if section_warnings:
            warnings[key] = section_warnings
    return warnings


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
    language_code    = (state.get("language_intent") or "en").lower()
    if language_code not in LANGUAGE_LABELS:
        logger.warning(
            f"MessagingAgent: Unknown language_intent '{language_code}' — falling back to English."
        )
        language_code = "en"
    language_name, language_style = LANGUAGE_LABELS[language_code]

    # Milestone L: strategic-frame mode toggle. Defensive normalization so a
    # malformed payload (None, unknown string) reverts to 'auto'.
    plan_mode = _normalize_plan_mode(state.get("plan_mode"))

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
    # Milestone H: research-backed social platform variants
    meta_instruction       = _get_format_instruction("meta_post")
    youtube_instruction    = _get_format_instruction("youtube_script")
    tiktok_instruction     = _get_format_instruction("tiktok_script")

    # -----------------------------------------------------------------------
    # 3. Single LLM call — all five formats, separated by section markers
    # -----------------------------------------------------------------------
    llm = get_completion_client(temperature=0.4)  # modest creativity for copywriting

    # Build the language directive. For non-English requests this is the single
    # most important instruction in the prompt — it goes BEFORE the hard
    # constraint so the model cannot accidentally fall back to English.
    if language_code == "en":
        language_directive = ""
    else:
        language_directive = (
            f"\u2501\u2501\u2501 LANGUAGE DIRECTIVE — NON-NEGOTIABLE \u2501\u2501\u2501\n"
            f"WRITE ALL EIGHT MESSAGING SECTIONS IN {language_name.upper()}.\n"
            f"Section headers, markers, and instructions stay in English; "
            f"all script content (greetings, talking points, CTAs, dialogue, "
            f"objection handling, ad copy) must be in {language_name}.\n"
            f"Do NOT translate the SECTION_MARKERS — keep them exactly as printed.\n"
            f"Do NOT include English versions or parenthetical translations.\n"
            f"{language_style.strip()}\n"
            f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n\n"
        )

    # Milestone L: build the strategic-frame directive and per-format CTA hints.
    # Both return empty strings in 'auto' mode, so the prompt is byte-identical
    # to pre-Milestone-L behavior when the user has not chosen a mode.
    mode_directive = _build_mode_directive(plan_mode)
    mode_cta_block = _build_mode_cta_block(plan_mode)

    prompt = f"""You are an expert field organizer and political messaging strategist.
Generate targeted campaign messaging materials for the {district_label}.

{language_directive}{mode_directive}━━━ HARD CONSTRAINT — READ CAREFULLY ━━━
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
Generate all eight sections below. Each section must:
1. Be grounded exclusively in the research findings above.
2. Be tailored to the demographic profile of the target precincts.
3. Close with this exact recency note in italics:
   *Research sourced from materials dated as recently as {most_recent_date}.*

You MUST include each section marker exactly as shown on its own line.
Do not rename, reorder, or omit any marker.

{mode_cta_block}{SECTION_MARKERS["canvassing_script"]}
{canvassing_instruction}

{SECTION_MARKERS["phone_script"]}
{phone_instruction}

{SECTION_MARKERS["text_script"]}
{text_instruction}

{SECTION_MARKERS["mail_narrative"]}
{mail_instruction}

{SECTION_MARKERS["digital_copy"]}
{digital_instruction}

{SECTION_MARKERS["meta_post"]}
{meta_instruction}

{SECTION_MARKERS["youtube_script"]}
{youtube_instruction}

{SECTION_MARKERS["tiktok_script"]}
{tiktok_instruction}
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
    # Surface the language in the header so the synthesizer (and any human
    # reviewer) can see at a glance which language was produced.
    lang_tag = f" | LANGUAGE: {language_name}" if language_code != "en" else ""
    mode_tag = f" | MODE: {MODE_LABELS[plan_mode]}" if plan_mode != "auto" else ""
    for key, label in FORMAT_LABELS.items():
        content = sections.get(key)
        if content:
            formatted_outputs.append(
                f"--- MESSAGING OUTPUT: {label} | DISTRICT: {district_label} "
                f"| RESEARCH DATE: {most_recent_date}{lang_tag}{mode_tag} ---\n{content}\n"
            )

    if not formatted_outputs:
        return {
            "errors":        ["MessagingAgent: LLM returned no parseable content."],
            "active_agents": ["messaging"],
        }

    # Milestone H: post-process social variants for hook + length checks.
    # Findings are warnings only — they don't block the output. They get
    # appended to the formatted footer so a reviewer can see at a glance
    # which variants drifted from format.
    social_warnings = check_social_format(sections)
    if social_warnings:
        logger.info(
            f"MessagingAgent: social variant format warnings: {social_warnings}"
        )
        # Annotate the matching formatted output with a small italic note.
        annotated: list[str] = []
        for chunk in formatted_outputs:
            extra = ""
            for fmt_key, warns in social_warnings.items():
                label = FORMAT_LABELS.get(fmt_key, "")
                if label and f"MESSAGING OUTPUT: {label}" in chunk:
                    extra = (
                        "\n\n*Format check:* "
                        + "; ".join(warns)
                        + "."
                    )
                    break
            annotated.append(chunk + extra if extra else chunk)
        formatted_outputs = annotated

    logger.info(
        f"MessagingAgent: Generated {len(formatted_outputs)}/8 messaging formats "
        f"for {district_label} in {language_name} (mode={plan_mode}) using research "
        f"dated as recently as {most_recent_date}."
    )

    return {
        "research_results": formatted_outputs,
        "active_agents":    ["messaging"],
    }
