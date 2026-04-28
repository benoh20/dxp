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
"""
from __future__ import annotations

import re
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
    Return one card per unique research memo, in original order, deduped on
    (source, date). Each card has: source, date, preview.

    Defensive: an empty or None input returns []. Memos that don't match the
    expected header format are skipped rather than raised, the researcher
    occasionally returns a fallback string and we don't want one bad row to
    break the UI.
    """
    if not research_results:
        return []

    cards: list[dict] = []
    seen: set[tuple[str, str]] = set()

    for memo in research_results:
        if not isinstance(memo, str):
            continue
        m = _MEMO_HEADER_RE.search(memo)
        if not m:
            continue
        source = m.group(1).strip()
        date = m.group(2).strip()
        key = (source.lower(), date.lower())
        if key in seen:
            continue
        seen.add(key)

        # Body is everything after the header line. Strip leading blank lines.
        body = memo[m.end():].lstrip()
        preview = body[:_PREVIEW_CHARS].rstrip()
        if len(body) > _PREVIEW_CHARS:
            preview += "\u2026"

        cards.append({
            "source":  source,
            "date":    date,
            "preview": preview,
        })

    return cards


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
