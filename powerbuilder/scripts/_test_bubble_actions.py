#!/usr/bin/env python
"""
Milestone E test suite — friendly error rendering + copy + regenerate.

Covers:
  1. friendly_error()    raw error string -> short user message
  2. sanitize_errors()   list-level dedup + filtering
  3. scrub_answer_text() strips agent error lines from final_answer
  4. partials/message.html renders bubble-actions + err-chip-row markup
  5. chat.html session-history loop renders the same affordances on
     restored messages, AND the delegated handler dispatches the two
     new actions (copy-answer + regenerate)

All assertions print PASS lines so the runner output is grepable. A
single failed assertion crashes with a clear AssertionError message.
"""
from __future__ import annotations

import os
import sys

import django

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "powerbuilder_app.settings")
django.setup()

from django.template.loader import render_to_string

from chat.render_helpers import (
    friendly_error,
    sanitize_errors,
    scrub_answer_text,
)


# ---------------------------------------------------------------------------
# 1. friendly_error()
# ---------------------------------------------------------------------------
def test_friendly_error():
    assertions = 0

    # OpenAI placeholder key — the exact case we saw in the audit screenshot
    raw_401 = (
        "MessagingAgent: LLM call failed - Error code: 401 - "
        "{'error': {'message': 'Incorrect API key provided: placeholder. "
        "You can find your API key at https://platform.openai.com/account/api-keys.', "
        "'type': 'invalid_request_error', 'param': None, 'code': 'invalid_api_key'}}"
    )
    msg = friendly_error(raw_401)
    assert "API key" in msg, f"expected API key message, got: {msg}"
    assert "Incorrect API key" not in msg, "raw text leaked: " + msg
    assert "401" not in msg, "status code leaked: " + msg
    assert "{'error'" not in msg, "raw dict leaked: " + msg
    assertions += 4

    # Rate limit
    msg = friendly_error("OpenAI returned 429 rate limit")
    assert "rate-limited" in msg.lower() or "rate limit" in msg.lower(), msg
    assertions += 1

    # Quota
    msg = friendly_error("insufficient_quota: You exceeded your current quota")
    assert "quota" in msg.lower(), msg
    assertions += 1

    # Generic 401 without "Incorrect API key"
    msg = friendly_error("ResearcherAgent: 401 Unauthorized")
    assert "authentication" in msg.lower() or "auth" in msg.lower(), msg
    assertions += 1

    # 403
    msg = friendly_error("403 Forbidden")
    assert "permission" in msg.lower(), msg
    assertions += 1

    # Pinecone
    msg = friendly_error("PineconeException: index not found")
    assert "Pinecone" in msg or "vector" in msg.lower(), msg
    assertions += 1

    # Network timeout
    msg = friendly_error("requests.exceptions.Timeout: timeout occurred")
    assert "timed out" in msg.lower() or "timeout" in msg.lower(), msg
    assertions += 1

    # Connection refused
    msg = friendly_error("ConnectionRefusedError: [Errno 111] Connection refused")
    assert "connection" in msg.lower(), msg
    assertions += 1

    # Generic LLM call failed (no other pattern matches)
    msg = friendly_error("PaidMediaAgent: LLM call failed - some opaque thing")
    assert "agent" in msg.lower() and "language model" in msg.lower(), msg
    assertions += 1

    # Unrecognised error -> generic fallback (still doesn't leak raw text)
    msg = friendly_error("Some random KeyError at line 42 in totally_unrelated.py")
    assert msg and "totally_unrelated" not in msg, msg
    assertions += 2

    # Defensive: None / empty -> empty string
    assert friendly_error(None) == ""
    assert friendly_error("") == ""
    assert friendly_error("   ") == ""
    assertions += 3

    print(f"  friendly_error: {assertions} assertions passed")


# ---------------------------------------------------------------------------
# 2. sanitize_errors()
# ---------------------------------------------------------------------------
def test_sanitize_errors():
    assertions = 0

    # Defensive
    assert sanitize_errors(None) == []
    assert sanitize_errors([]) == []
    assertions += 2

    # Two raw 401s from different agents collapse to one user message
    raws = [
        "MessagingAgent: LLM call failed - Error code: 401 - {'error': {'message': 'Incorrect API key provided: placeholder.'}}",
        "ExportAgent: LLM synthesis failed - Error code: 401 - {'error': {'message': 'Incorrect API key provided: placeholder.'}}",
    ]
    out = sanitize_errors(raws)
    assert len(out) == 1, f"expected dedup, got {out}"
    assert "API key" in out[0], out[0]
    assertions += 2

    # Mixed bag
    raws = [
        "OpenAI returned 429 rate limit",
        "PineconeException: index not found",
        "OpenAI returned 429 rate limit",  # dup
    ]
    out = sanitize_errors(raws)
    assert len(out) == 2, f"expected 2 unique, got {out}"
    assertions += 1

    # Empty strings filtered
    out = sanitize_errors(["", None, "   ", "401 unauthorized"])
    assert len(out) == 1, f"expected 1 entry, got {out}"
    assertions += 1

    print(f"  sanitize_errors: {assertions} assertions passed")


# ---------------------------------------------------------------------------
# 3. scrub_answer_text()
# ---------------------------------------------------------------------------
def test_scrub_answer_text():
    assertions = 0

    # Defensive
    assert scrub_answer_text(None) == ""
    assert scrub_answer_text("") == ""
    assertions += 2

    # The exact bug from the audit: synthesizer pasted error lines at the top
    polluted = (
        "⚠️ MessagingAgent: LLM call failed — Error code: 401 - {'error': {'message': 'Incorrect API key provided'}}\n"
        "⚠️ ExportAgent: LLM synthesis failed — Error code: 401 - {'error': {'message': 'Incorrect API key provided'}}\n"
        "\n"
        "# Real Plan Title\n"
        "\n"
        "Body content goes here.\n"
    )
    cleaned = scrub_answer_text(polluted)
    assert "MessagingAgent" not in cleaned, "MessagingAgent line leaked: " + cleaned
    assert "ExportAgent" not in cleaned, "ExportAgent line leaked: " + cleaned
    assert "401" not in cleaned, "status code leaked"
    assert "Real Plan Title" in cleaned, "real content was stripped"
    assert "Body content goes here." in cleaned, "real body was stripped"
    assertions += 5

    # Plain prose with the word "failed" must NOT be touched
    safe = "The campaign failed to win in 2022 because of low turnout."
    assert scrub_answer_text(safe) == safe, "false-positive scrubbed prose"
    assertions += 1

    # Multiple consecutive blank lines from the strip get collapsed to 2
    cleaned = scrub_answer_text(polluted)
    assert "\n\n\n" not in cleaned, "blank lines not collapsed"
    assertions += 1

    # Single warning line at the top is removed and content starts cleanly
    cleaned = scrub_answer_text("⚠️ ResearcherAgent: LLM call failed — bla bla\n\n# Title")
    assert cleaned.startswith("# Title"), "leading whitespace not stripped: " + repr(cleaned)
    assertions += 1

    print(f"  scrub_answer_text: {assertions} assertions passed")


# ---------------------------------------------------------------------------
# 4. partials/message.html renders new affordances
# ---------------------------------------------------------------------------
def test_partial_renders_actions_and_chips():
    assertions = 0

    ctx = {
        "answer_html": "<p>Hello world</p>",
        "active_agents": ["researcher"],
        "errors": ["Couldn't reach the language model: API key isn't configured. Set OPENAI_API_KEY in the environment."],
        "bubble_id": "b-test1234",
        "outline": {"show_panel": False},
    }
    html = render_to_string("partials/message.html", ctx)

    # Bubble action row present
    assert 'class="bubble-actions"' in html, "missing bubble-actions row"
    assert 'data-action="copy-answer"' in html, "missing copy-answer button"
    assert 'data-action="regenerate"' in html, "missing regenerate button"
    assertions += 3

    # Friendly error chip rendered. Django auto-escapes apostrophes to &#x27;
    # so we compare on the unescaped version of the rendered HTML.
    import html as _html
    html_text = _html.unescape(html)
    assert 'class="err-chip-row"' in html, "missing err-chip-row"
    assert 'class="err-chip"' in html, "missing err-chip"
    assert "API key isn't configured" in html_text, "error text not surfaced"
    assertions += 3

    # Old italic-muted style is GONE
    assert "font-style:italic" not in html, "old italic error style still present"
    assertions += 1

    # When errors empty, chip row absent but action row still shown
    ctx_no_err = dict(ctx); ctx_no_err["errors"] = []
    html2 = render_to_string("partials/message.html", ctx_no_err)
    assert 'class="err-chip-row"' not in html2, "chip row leaked when no errors"
    assert 'data-action="copy-answer"' in html2, "actions hidden when no errors"
    assertions += 2

    print(f"  partial markup: {assertions} assertions passed")


# ---------------------------------------------------------------------------
# 5. chat.html session-history + delegated handler
# ---------------------------------------------------------------------------
def test_chat_html_handler_and_history():
    assertions = 0

    chat_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "templates", "chat.html",
    )
    src = open(chat_path).read()

    partial_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "templates", "partials", "message.html",
    )
    partial_src = open(partial_path).read()

    # Session-history asst branch (in chat.html) AND the live partial both
    # render the action row, so a restored conversation and a freshly
    # streamed message look identical.
    assert 'data-action="copy-answer"' in src, \
        "session-history copy-answer button missing in chat.html"
    assert 'data-action="regenerate"' in src, \
        "session-history regenerate button missing in chat.html"
    assert 'data-action="copy-answer"' in partial_src, \
        "copy-answer button missing in partials/message.html"
    assert 'data-action="regenerate"' in partial_src, \
        "regenerate button missing in partials/message.html"
    assertions += 4

    # Session history has err-chip-row for restored msg.errors
    assert "msg.errors" in src and ".err-chip-row" in src, \
        "session-history error rendering missing"
    assertions += 1

    # Delegated handler dispatches both new actions
    assert "if (action === 'copy-answer')" in src, "copy handler missing"
    assert "if (action === 'regenerate')" in src, "regenerate handler missing"
    assertions += 2

    # Copy handler uses navigator.clipboard with execCommand fallback
    assert "navigator.clipboard" in src, "modern clipboard path missing"
    assert "execCommand('copy')" in src, "fallback path missing"
    assertions += 2

    # Copy reads from .prose-dark (clean text, no HTML)
    assert ".prose-dark" in src and "innerText" in src, \
        "copy must pull clean innerText from .prose-dark"
    assertions += 1

    # Regenerate walks back to the prior user row and arms rerun mode
    assert "previousElementSibling" in src, "regenerate must walk previous siblings"
    assert "setRerunMode(true" in src, "regenerate must arm rerun mode"
    assert "requestSubmit" in src, "regenerate must auto-submit"
    assertions += 3

    # CSS exists for the new affordances
    assert ".bubble-actions" in src and ".bubble-action-btn" in src, \
        "bubble-actions CSS missing"
    # Milestone O: tokenized warning palette. Accept either the legacy raw
    # rgba (pre-O) or the new --warning-soft-* token aliases.
    assert ".err-chip" in src and (
        "rgba(245,158,11" in src
        or "--warning-soft-bg" in src
        or "--warning-soft-border" in src
    ), "err-chip CSS missing or wrong tone"
    assertions += 2

    # Mobile keeps actions visible at lower opacity
    assert ".bubble-actions { opacity: 0.85" in src, \
        "mobile bubble-actions visibility rule missing"
    assertions += 1

    print(f"  chat.html wiring: {assertions} assertions passed")


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("Milestone E: friendly errors + copy + regenerate")
    test_friendly_error()
    test_sanitize_errors()
    test_scrub_answer_text()
    test_partial_renders_actions_and_chips()
    test_chat_html_handler_and_history()
    print("PASS: all assertion groups OK.")
