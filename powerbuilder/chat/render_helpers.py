"""
Render-time helpers shared by the streaming and HTMX views.

extract_sources()  parses the researcher's "MEMO FROM SOURCE: ..." preamble
                   into a deduplicated list of source cards for the UI.
is_plan_run()      heuristic: did this run produce a multi-agent plan?
                   Used to decide whether to show the C3-safe footer.
agent_pill_label() prettifies internal node names ("opposition_research"
                   becomes "Opposition Research") for the agent pill row.
auto_title()       turns a raw user query into a short, sidebar-friendly
                   conversation title (drops filler words, title-cases).
download_thumb_kind() maps a filename to a (kind, color) tuple for the
                   download-card thumbnail badge.
plan_outline()     builds a sectioned outline of a plan response (markdown
                   headings, agents, sources, downloads) for the side panel.
"""
from __future__ import annotations

import re
import time as _time
from typing import Iterable


# Researcher prepends each memo with:
#   --- MEMO FROM SOURCE: <source> | DATE: <date> ---
# This regex is anchored at line start so it does not match inside body text.
_MEMO_HEADER_RE = re.compile(
    r"^---\s*MEMO\s+FROM\s+SOURCE:\s*(.+?)\s*\|\s*DATE:\s*(.+?)\s*---\s*$",
    re.MULTILINE | re.IGNORECASE,
)

# A short body preview shown when the user expands a source card. Long enough
# to give context, short enough to keep the UI tidy.
_PREVIEW_CHARS = 320


def extract_sources(research_results: Iterable[str] | None) -> list[dict]:
    """
    Return one card per unique source, in first-seen order.

    The corpus is chunked, so the same source string typically shows up many
    times with different DATE stamps (one per chunk file). Showing nine
    'Powerbuilder curated corpus...' cards in a row was the audit finding
    behind this milestone, so we collapse on source identity (case-insensitive)
    and roll the dates up onto a single card.

    Each card has:
        source   normalised (whitespace-collapsed) source string
        date     the most recent date if multiple were seen, else the only date
        date_range  human-readable span when more than one date rolled up
                    (e.g. '2024-11-12 → 2025-09-15'); empty string otherwise
        count    how many memos rolled up into this card (>= 1)
        preview  body preview from the FIRST memo seen for this source

    Defensive: empty or None input returns []. Memos missing the standard
    header are skipped rather than raised; the researcher occasionally returns
    a fallback string and we don't want one bad row to break the UI.
    """
    if not research_results:
        return []

    by_source: dict[str, dict] = {}
    order: list[str] = []

    for memo in research_results:
        if not isinstance(memo, str):
            continue
        m = _MEMO_HEADER_RE.search(memo)
        if not m:
            continue
        source = _normalise_ws(m.group(1).strip())
        date = m.group(2).strip()
        key = source.lower()

        body = memo[m.end():].lstrip()
        preview = body[:_PREVIEW_CHARS].rstrip()
        if len(body) > _PREVIEW_CHARS:
            preview += "\u2026"

        if key not in by_source:
            by_source[key] = {
                "source":  source,
                "dates":   [date],
                "preview": preview,
            }
            order.append(key)
        else:
            entry = by_source[key]
            if date not in entry["dates"]:
                entry["dates"].append(date)

    cards: list[dict] = []
    for key in order:
        entry  = by_source[key]
        dates  = entry["dates"]
        sorted_dates = _sorted_dates(dates)
        primary = sorted_dates[-1] if sorted_dates else (dates[0] if dates else "")
        if len(sorted_dates) > 1:
            date_range = f"{sorted_dates[0]} → {sorted_dates[-1]}"
        else:
            date_range = ""
        cards.append({
            "source":     entry["source"],
            "date":       primary,
            "date_range": date_range,
            "count":      len(dates),
            "preview":    entry["preview"],
        })
    return cards


_WS_RE = re.compile(r"\s+")


def _normalise_ws(s: str) -> str:
    """Collapse runs of whitespace so 'foo  bar' and 'foo bar' merge."""
    return _WS_RE.sub(" ", s).strip()


_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _sorted_dates(dates: list[str]) -> list[str]:
    """
    Return the dates sorted ascending where possible. Pure-ISO strings sort
    lexicographically (which matches chronological order); free-form strings
    fall to the end in original order so we don't crash on 'date unknown'.
    """
    iso  = sorted(d for d in dates if _ISO_DATE_RE.match(d))
    rest = [d for d in dates if not _ISO_DATE_RE.match(d)]
    return iso + rest


# Active agents that, when present, indicate a full plan run rather than a
# single-topic answer. We surface the C3-safe disclosure only on plans,
# generic factual answers don't need it.
_PLAN_AGENTS = {"win_number", "precincts", "cost_calculator", "messaging"}


def is_plan_run(active_agents: Iterable[str] | None) -> bool:
    """
    Heuristic: a run is a "plan" if at least two of the plan-shape agents
    fired. One agent on its own is a single-topic answer (e.g. a quick
    win-number lookup, or messaging-only) and doesn't carry the same
    compliance weight.
    """
    if not active_agents:
        return False
    return len(_PLAN_AGENTS.intersection(active_agents)) >= 2


_C3_FOOTER_TEXT = (
    "Nonpartisan voter education. Not for candidate or party support."
)


def c3_footer_text() -> str:
    """Single source of truth for the C3-safe disclosure string."""
    return _C3_FOOTER_TEXT


def agent_pill_label(node_name: str) -> str:
    """
    Prettify an internal node name for display in the agent pill row.
    Examples:
        researcher           becomes Researcher
        opposition_research  becomes Opposition Research
        cost_calculator      becomes Cost Calculator
    """
    if not node_name:
        return ""
    return node_name.replace("_", " ").title()


# Filler words stripped by auto_title(). Lower-cased; only matches whole tokens.
# Keeps proper nouns and numbers ("GA-07", "Gwinnett", "18-35") intact.
_TITLE_STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "if", "so",
    "of", "in", "on", "at", "to", "for", "with", "by", "from", "as", "into",
    "is", "are", "was", "were", "be", "been", "being",
    "do", "does", "did", "can", "could", "should", "would", "will", "shall",
    "i", "me", "my", "we", "our", "us", "you", "your",
    "please", "could", "would", "need",
    "give", "show", "tell", "make", "build", "create", "draft", "write",
    "help", "like",
    # Common lead-ins that add no signal to a title.
    "how", "what", "why", "when", "where", "who", "which",
}

_TITLE_MAX_WORDS = 6
_TITLE_MAX_CHARS = 48

# Tokenizer keeps hyphens (GA-07), apostrophes (don't), and digits inside words.
_TITLE_TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9'\-]*")


def auto_title(query: str) -> str:
    """
    Turn a raw user query into a short conversation title for the sidebar.

    Strategy: tokenize, drop filler stop-words, keep up to 6 meaningful
    tokens, title-case proper-noun-style, cap total length at 48 chars.
    Falls back to the raw truncated query when the result would be empty
    (very short or all-stopword queries like "hi").

    Examples:
        "What is the win number for GA-07 in the midterm?"
            becomes  "Win Number GA-07 Midterm"
        "Please draft a Spanish door-knock script for Latinx voters"
            becomes  "Spanish Door-Knock Script Latinx Voters"
        "hi"
            becomes  "hi"  (fallback)
    """
    if not query or not query.strip():
        return "New conversation"

    tokens = _TITLE_TOKEN_RE.findall(query)
    kept: list[str] = []
    for tok in tokens:
        if tok.lower() in _TITLE_STOPWORDS:
            continue
        kept.append(tok)
        if len(kept) >= _TITLE_MAX_WORDS:
            break

    # Fallback: stop-word soup or single-token greeting becomes raw truncate.
    if not kept:
        cleaned = query.strip()
        return cleaned[:_TITLE_MAX_CHARS] if cleaned else "New conversation"

    # Preserve all-caps acronyms and codes ("GA-07", "AAPI", "GOTV").
    def _cap(token: str) -> str:
        if token.isupper() or any(c.isdigit() for c in token):
            return token
        # Hyphenated words: capitalize each part ("door-knock" -> "Door-Knock").
        if "-" in token:
            return "-".join(p[:1].upper() + p[1:].lower() if p else p for p in token.split("-"))
        return token[:1].upper() + token[1:].lower()

    title = " ".join(_cap(t) for t in kept)
    if len(title) > _TITLE_MAX_CHARS:
        title = title[: _TITLE_MAX_CHARS - 1].rstrip() + "\u2026"
    return title


# Maps file extension to (kind label, accent color hex). The thumbnail badge
# in download cards uses these so the operator can scan a row of artifacts
# at a glance without reading filenames.
_THUMB_KINDS = {
    "docx": ("DOCX", "#3b82f6"),  # blue, matches plan/full-doc category
    "doc":  ("DOC",  "#3b82f6"),
    "csv":  ("CSV",  "#22c55e"),  # green, matches data/list category
    "xlsx": ("XLSX", "#16a34a"),
    "xls":  ("XLS",  "#16a34a"),
    "pdf":  ("PDF",  "#ef4444"),  # red, matches research/source category
    "txt":  ("TXT",  "#6b7280"),  # gray fallback
    "md":   ("MD",   "#6b7280"),
    "json": ("JSON", "#a855f7"),
}


def download_thumb_kind(filename: str | None) -> dict:
    """
    Return {kind, color} for the thumbnail badge of a download card.

    Defaults to a neutral 'FILE' badge when the extension is unknown or
    the filename is missing. The color is intended for both the badge
    background (with low opacity) and the text/border (full opacity);
    the template handles the alpha mixing.
    """
    if not filename:
        return {"kind": "FILE", "color": "#6b7280"}
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    kind, color = _THUMB_KINDS.get(ext, ("FILE", "#6b7280"))
    return {"kind": kind, "color": color}


def enrich_downloads(downloads: list[dict] | None) -> list[dict]:
    """
    Return a new list of download dicts with thumbnail metadata attached.

    Each item gains 'thumb_kind' and 'thumb_color' keys without mutating
    the input. Items missing 'filename' are passed through with the neutral
    FILE badge so the template can still render them.
    """
    if not downloads:
        return []
    out = []
    for d in downloads:
        if not isinstance(d, dict):
            continue
        thumb = download_thumb_kind(d.get("filename"))
        out.append({
            **d,
            "thumb_kind":  thumb["kind"],
            "thumb_color": thumb["color"],
        })
    return out


# Heading-id prefix injector (Milestone D). Multiple assistant bubbles can
# share heading text ("Strategy"), which would create duplicate DOM ids and
# break the side-panel anchor links. We prefix every id="..." on h1/h2/h3
# with the bubble's unique id so anchors land on the right bubble.
_HEADING_ID_RE = re.compile(
    r'(<h[1-3]\b[^>]*?)\sid="([^"]+)"',
    re.IGNORECASE,
)


def prefix_heading_ids(html: str | None, bubble_id: str | None) -> str:
    """
    Prefix every <h1|h2|h3 id="slug"> inside ``html`` with ``bubble_id`` so
    each rendered bubble has its own anchor namespace. Pure (returns a new
    string), defensive on missing inputs.
    """
    if not html or not bubble_id:
        return html or ""
    def _sub(m: re.Match) -> str:
        return f'{m.group(1)} id="{bubble_id}-{m.group(2)}"'
    return _HEADING_ID_RE.sub(_sub, html)


# ---------------------------------------------------------------------------
# Plan outline (Milestone D: plan-panel split view)
# ---------------------------------------------------------------------------
#
# A plan response is a multi-section markdown document covering targeting,
# messaging, cost, sources, etc. The side panel needs a structured outline
# so the operator can scan what landed and jump to a section. We do this
# without taxing the agents: the markdown headings already carry the
# section names, and the agents/sources/downloads counts give us anchored
# meta-rows even if a heading was missed.

# Match ATX-style markdown headings (#, ##, ###). Block start only, so we do
# not pick up '#' inside fenced code blocks (we strip those first).
_HEADING_RE = re.compile(r"^(#{1,3})\s+(.+?)\s*#*\s*$", re.MULTILINE)

# Strip fenced code blocks before scanning headings — fenced bodies can
# contain '#' in shell prompts, comments, etc., and we never want them.
_FENCED_RE = re.compile(r"```.*?```", re.DOTALL)

# Slug pattern: lowercase, dash-joined, ascii-only. Mirrors what
# python-markdown's TOC extension would generate so links match.
_SLUG_DROP_RE = re.compile(r"[^a-z0-9\s\-]+")
_SLUG_WS_RE   = re.compile(r"[\s\-]+")


def _slugify_heading(text: str) -> str:
    """Slugify a heading the same way the chat bubble does for anchors."""
    if not text:
        return ""
    s = text.strip().lower()
    s = _SLUG_DROP_RE.sub("", s)
    s = _SLUG_WS_RE.sub("-", s)
    return s.strip("-")


def plan_outline(
    final_answer: str | None,
    active_agents: Iterable[str] | None = None,
    source_cards: Iterable[dict] | None = None,
    downloads: Iterable[dict] | None = None,
) -> dict:
    """
    Build the data shape the plan-panel template renders.

    Returns a dict with:
        is_plan: bool      — did this run earn a panel?
        sections: list     — [{level, text, slug}] for every #/##/### heading
        agents: list       — prettified active agent labels
        source_count: int  — for the meta-row badge
        download_count: int

    The panel is shown only when is_plan is True AND we found at least one
    heading or have multiple agents to surface. Single-topic answers
    (a one-shot win-number lookup) get nothing, which is the right call:
    they don't need a navigation aid.
    """
    agents_list = list(active_agents or [])
    is_plan = is_plan_run(agents_list)

    sections: list[dict] = []
    if final_answer:
        scrubbed = _FENCED_RE.sub("", final_answer)
        for m in _HEADING_RE.finditer(scrubbed):
            level = len(m.group(1))
            text  = m.group(2).strip()
            if not text:
                continue
            sections.append({
                "level": level,
                "text":  text,
                "slug":  _slugify_heading(text),
            })

    source_count   = sum(1 for _ in (source_cards or []))
    download_count = sum(1 for _ in (downloads or []))

    # Show the panel only when there is real outline value: a plan run AND
    # either a couple of headings OR a couple of agents to label. This
    # avoids a near-empty side rail on borderline responses.
    has_structure = len(sections) >= 2 or len(agents_list) >= 3
    show_panel    = bool(is_plan and has_structure)

    return {
        "is_plan":        bool(is_plan),
        "show_panel":     show_panel,
        "sections":       sections,
        "groups":         _group_sections_by_h1(sections),
        "agents":         [agent_pill_label(a) for a in agents_list],
        "source_count":   source_count,
        "download_count": download_count,
    }


def _group_sections_by_h1(sections: list[dict]) -> list[dict]:
    """
    Group flat outline sections under their h1 anchors for the panel UI
    (Milestone G). Returns a list shaped like:

        [
          {"h1": {level, text, slug} | None,    # None == synthetic top group
           "children": [{level, text, slug}, ...]},
          ...
        ]

    Rules:
      - Sections appearing before the first h1 land in a synthetic 'h1=None'
        group at the top, so they don't get orphaned. The template renders
        that group without a header.
      - Each h1 owns every following section (h2, h3, ...) until the next
        h1, regardless of nesting depth. We keep h2/h3/... distinction
        intact via the existing 'level' field; the template applies the
        same indent classes it always has.
      - If there are zero h1s anywhere, we return a single synthetic group
        containing every section so the existing flat-list behaviour is
        preserved for shorter plans.
    """
    groups: list[dict] = []
    current: dict | None = None
    for s in sections:
        if s["level"] == 1:
            current = {"h1": s, "children": []}
            groups.append(current)
            continue
        if current is None:
            # Sub-headings before the first h1: open a synthetic group
            current = {"h1": None, "children": []}
            groups.append(current)
        current["children"].append(s)
    return groups


# ---------------------------------------------------------------------------
# Relative time formatting (Milestone F: sidebar timestamps)
# ---------------------------------------------------------------------------
#
# The sidebar shows a small timestamp under each conversation title. The old
# fixed string ('2026-04-28 09:00') ages poorly: a conversation from this
# morning and one from last week look the same. relative_time() collapses
# anything within the last week into a short phrase ('Just now', '5m ago',
# '2h ago', 'Yesterday') and falls back to a 'Mon DD' calendar tag for older
# entries. Pure (takes a Unix int, returns a string), no Django dependency.

_MONTH_ABBR = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
               "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def relative_time(ts: int | float | None, now: int | float | None = None) -> str:
    """
    Convert a Unix timestamp into a short human label suitable for the sidebar.

    Buckets:
        < 60s        becomes  'Just now'
        < 60m        becomes  'Nm ago'
        < 24h        becomes  'Nh ago'
        same calendar day before that  becomes  'Yesterday'
        < 7 days     becomes  'Nd ago'
        else         becomes  'Mon DD' (e.g. 'Apr 28')

    Defensive: None or non-numeric input returns ''. Future timestamps clamp
    to 'Just now' so a small clock skew between client and server doesn't
    surface a negative duration.

    The optional 'now' parameter exists so tests can pin the wall clock
    instead of monkey-patching time.
    """
    if ts is None:
        return ""
    try:
        ts = int(ts)
    except (TypeError, ValueError):
        return ""
    now_i = int(now) if now is not None else int(_time.time())
    delta = now_i - ts
    if delta < 60:
        return "Just now"
    if delta < 3600:
        return f"{delta // 60}m ago"
    if delta < 86400:
        return f"{delta // 3600}h ago"
    # Day-of-year boundary: 'Yesterday' fires only if the calendar date
    # actually flipped, not just because 24h elapsed.
    now_struct = _time.localtime(now_i)
    ts_struct  = _time.localtime(ts)
    days_ago = (now_struct.tm_yday - ts_struct.tm_yday) % 366
    if now_struct.tm_year != ts_struct.tm_year:
        # Cross-year wrap: fall through to absolute formatting below.
        days_ago = 9_999
    if days_ago == 1:
        return "Yesterday"
    if delta < 7 * 86400 and days_ago < 7:
        return f"{days_ago}d ago"
    return f"{_MONTH_ABBR[ts_struct.tm_mon - 1]} {ts_struct.tm_mday:02d}"


# ---------------------------------------------------------------------------
# Friendly error rendering (Milestone E)
# ---------------------------------------------------------------------------
#
# Agents return raw exception strings on failure, and the synthesizer LLM
# sometimes echoes those into the rendered answer. Both surfaces leak ugly
# stacktraces ("Error code: 401 - {'error': {'message': 'Incorrect API key
# provided: placeholder. ...'}}") into the UI.
#
# friendly_error()    maps a raw error string to a short, human message
# sanitize_errors()   maps a list of raw errors via friendly_error and dedupes
# scrub_answer_text() removes ⚠ AgentName: LLM call failed... lines that the
#                     synthesizer occasionally pastes into final_answer
#
# All three are pure functions, defensive on None/empty inputs, and don't
# import anything from Django or the agent layer so they're easy to test.

# Patterns: (regex_or_substring, friendly_message)
# Order matters: first match wins, so put more specific patterns first.
_ERROR_PATTERNS = [
    # OpenAI: invalid key (placeholder or rotated)
    (re.compile(r"Incorrect API key provided", re.IGNORECASE),
     "Couldn't reach the language model: API key isn't configured. Set OPENAI_API_KEY in the environment."),
    (re.compile(r"invalid_api_key|invalid_request_error.*api[_ ]key", re.IGNORECASE),
     "Couldn't reach the language model: API key was rejected."),
    # OpenAI: rate / quota
    (re.compile(r"rate.?limit|429", re.IGNORECASE),
     "The language model is rate-limited right now, try again in a moment."),
    (re.compile(r"insufficient_quota|exceeded.*quota", re.IGNORECASE),
     "The language model account is out of quota."),
    # OpenAI: auth other than key
    (re.compile(r"\b401\b|unauthorized", re.IGNORECASE),
     "Couldn't reach the language model: authentication failed."),
    (re.compile(r"\b403\b|forbidden", re.IGNORECASE),
     "Couldn't reach the language model: permission denied."),
    # Pinecone
    (re.compile(r"pinecone", re.IGNORECASE),
     "Couldn't reach the vector database (Pinecone). Continuing without retrieval."),
    # Network
    (re.compile(r"timeout|timed out", re.IGNORECASE),
     "A request timed out, the response may be incomplete."),
    (re.compile(r"connection.*refused|connection.*reset|connection.*aborted", re.IGNORECASE),
     "A network connection failed, the response may be incomplete."),
    # Generic LLM failure (catch-all if "LLM call failed" but no other pattern matched)
    (re.compile(r"LLM call failed", re.IGNORECASE),
     "One of the agents couldn't reach its language model, the response may be incomplete."),
]


# Generic fallback chip: shown when an agent error didn't match any specific
# pattern. Loud enough to flag a real outage, useless when the answer renders
# fine because some optional API key (Census, FEC) is missing on a preview
# environment. We expose this string so the view layer can filter it out when
# the deliverable looks complete.
GENERIC_ERROR_FALLBACK = "An agent reported an issue, the response may be incomplete."


def friendly_error(raw: str | None) -> str:
    """
    Map a raw agent-error string to a short, user-readable message.

    Examples:
        "MessagingAgent: LLM call failed - Error code: 401 - {'error': {'message': 'Incorrect API key provided: placeholder. ...'}}"
        becomes
        "Couldn't reach the language model: API key isn't configured. Set OPENAI_API_KEY in the environment."

    Defensive: None or empty string returns "" so callers can filter out empties.
    Unrecognised errors get a generic fallback rather than the raw text.
    """
    if not raw:
        return ""
    s = str(raw).strip()
    if not s:
        return ""
    for pattern, friendly in _ERROR_PATTERNS:
        if pattern.search(s):
            return friendly
    # Fallback: keep it short and don't leak the raw string. Most users want to
    # know SOMETHING happened, not the full stacktrace.
    return GENERIC_ERROR_FALLBACK


# Heuristic: when the markdown answer renders to at least this many characters
# of HTML the deliverable is "meaningful" and we can drop the generic-fallback
# chip. Tuned so a one-line apology stays flagged but a real briefing (intro +
# theory of change + at least one section) clears the bar.
_MEANINGFUL_ANSWER_MIN_CHARS = 200


def has_meaningful_answer(answer_html: str | None) -> bool:
    """
    True when ``answer_html`` looks like a real rendered response rather than
    an empty / placeholder bubble. We measure raw length because the answer is
    already markdown-rendered HTML by the time the view checks it; even a
    short briefing easily clears 200 chars once headings + paragraph wrappers
    are counted.
    """
    if not answer_html:
        return False
    return len(answer_html) >= _MEANINGFUL_ANSWER_MIN_CHARS


def sanitize_errors(
    errors: Iterable[str] | None,
    *,
    answer_html: str | None = None,
) -> list[str]:
    """
    Return a list of friendly error messages, deduplicated, in original order.
    Empty / None input returns []. Empty individual entries are dropped.

    When ``answer_html`` is provided AND looks like a meaningful deliverable
    (see :func:`has_meaningful_answer`), the generic-fallback chip is dropped.
    Specific chips (auth failures, rate limits, missing keys) still surface so
    the operator knows when something genuinely degraded the answer. Callers
    that don't pass ``answer_html`` get the legacy behaviour: every chip is
    kept.
    """
    if not errors:
        return []
    suppress_generic = answer_html is not None and has_meaningful_answer(answer_html)
    out: list[str] = []
    seen: set[str] = set()
    for raw in errors:
        msg = friendly_error(raw)
        if not msg or msg in seen:
            continue
        if suppress_generic and msg == GENERIC_ERROR_FALLBACK:
            continue
        seen.add(msg)
        out.append(msg)
    return out


# A line that starts (after optional whitespace) with the warning glyph followed
# by an AgentName-style identifier and then "LLM call failed" or similar. The
# synthesizer occasionally pastes these into the final answer when it sees the
# error_block in the prompt. We strip them before markdown render.
_ANSWER_ERROR_LINE_RE = re.compile(
    r"""
    ^[ \t]*                              # leading whitespace
    \u26A0\uFE0F?                        # ⚠ optionally followed by VS16 (⚠️)
    [ \t]*                               #
    [A-Z][A-Za-z]*Agent                  # ResearcherAgent, MessagingAgent, ExportAgent, ...
    [ \t]*[:\-\u2014][ \t]*              # separator: colon, dash, em-dash
    .*?                                  # anything (e.g. "LLM call", "LLM synthesis", ...)
    failed                               # the failure word
    .*$                                  # to end of line
    """,
    re.MULTILINE | re.VERBOSE | re.IGNORECASE,
)


def scrub_answer_text(text: str | None) -> str:
    """
    Remove agent-error lines that the synthesizer occasionally echoes into
    the rendered answer. Returns the cleaned text. None / empty returns "".

    Only strips lines that match the warning + AgentName + "LLM call failed"
    pattern, so plain prose with the word "failed" is left alone.

    The friendly versions of these errors are shown separately under the
    answer via sanitize_errors(), so the user still knows something went
    wrong, they just don't see the raw 401 JSON dump.
    """
    if not text:
        return ""
    # Strip the offending lines plus any blank line they leave behind
    cleaned = _ANSWER_ERROR_LINE_RE.sub("", text)
    # Collapse 3+ consecutive newlines that the removal may have created
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.lstrip()
