"""
Demo-polish tests covering three fixes:

  1. SSE session persistence — _build_done_payload() must explicitly save the
     session (StreamingHttpResponse + SessionMiddleware would otherwise lose
     the conversation history because process_response runs before the
     generator yields).

  2. Generic err-chip filtering — sanitize_errors(answer_html=...) drops the
     generic "agent reported an issue" fallback when the answer is meaningful
     while still surfacing specific chips (auth, rate-limit, quota).

  3. Toggle strings — THEME / System / Light / Dark, A/B toggle hint, and Mode
     toggle hints are wrapped in {% trans %} and the ES + VI catalogues carry
     translations for every one.

Test files print a PASS line per section and finish with
``ALL PASS — N assertions``.
"""
from __future__ import annotations

import html
import os
import re
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "powerbuilder_app.settings")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-validation-only")
os.environ["DEBUG"] = "True"
os.environ.setdefault("DEMO_PASSWORD", "fieldwork-mobilize-78")
os.environ["ALLOWED_HOSTS"] = "testserver,localhost,127.0.0.1"

import django  # noqa: E402

django.setup()

from chat import render_helpers as rh  # noqa: E402
from chat import views as chat_views  # noqa: E402

assertions = 0


def assert_(cond: bool, label: str) -> None:
    global assertions
    assertions += 1
    if not cond:
        raise AssertionError(f"FAIL: {label}")


# ────────────────────────────────────────────────────────────────────────────
# Section 1 — generic err-chip filtering
# ────────────────────────────────────────────────────────────────────────────

GENERIC = rh.GENERIC_ERROR_FALLBACK
SHORT_HTML = "<p>Sorry, no answer.</p>"
LONG_HTML = (
    "<h1>Win Number for HD-104</h1>"
    "<h2>Theory of Change</h2>"
    "<p><strong>If we identify and turn out 8,400 supporters in HD-104, "
    "we win the seat by mobilizing the universe we already have.</strong></p>"
    "<h2>What we know</h2>"
    "<p>Recent two-cycle average suggests a turnout floor of about 16,800 voters.</p>"
)

# 1a. Default behaviour (no answer_html arg) keeps the generic chip — back-compat.
errs_default = rh.sanitize_errors(["VoterFileAgent: something obscure happened"])
assert_(GENERIC in errs_default, "default sanitize keeps generic chip")
print("PASS  generic chip kept when answer_html is not provided  (1 assertion)")

# 1b. Meaningful answer suppresses the generic fallback.
errs_full = rh.sanitize_errors(
    ["VoterFileAgent: something obscure happened"],
    answer_html=LONG_HTML,
)
assert_(GENERIC not in errs_full, "generic chip dropped when answer is meaningful")
assert_(errs_full == [], "no chips at all when only generic-fallback fired and answer is fine")
print("PASS  generic chip suppressed for a meaningful answer  (2 assertions)")

# 1c. Empty / short answer keeps the generic fallback (operator needs to know).
errs_short = rh.sanitize_errors(
    ["VoterFileAgent: something obscure happened"],
    answer_html=SHORT_HTML,
)
assert_(GENERIC in errs_short, "generic chip kept when answer is short")
errs_empty = rh.sanitize_errors(
    ["VoterFileAgent: something obscure happened"],
    answer_html="",
)
assert_(GENERIC in errs_empty, "generic chip kept when answer is empty")
print("PASS  generic chip kept when answer is empty / minimal  (2 assertions)")

# 1d. Specific chips ALWAYS surface, even with a meaningful answer.
specific_inputs = [
    "MessagingAgent: LLM call failed - Error code: 401 - Incorrect API key provided: placeholder",
    "RateLimitError: 429 too many requests",
    "Pinecone: index not found",
]
errs_specific = rh.sanitize_errors(specific_inputs, answer_html=LONG_HTML)
assert_(any("API key" in m for m in errs_specific), "auth chip still shown")
assert_(any("rate-limited" in m or "rate limit" in m.lower() for m in errs_specific), "rate-limit chip still shown")
assert_(any("Pinecone" in m for m in errs_specific), "Pinecone chip still shown")
assert_(GENERIC not in errs_specific, "generic chip not added alongside specific ones")
print("PASS  specific chips still surface alongside meaningful answer  (4 assertions)")

# 1e. has_meaningful_answer threshold sanity.
assert_(rh.has_meaningful_answer(LONG_HTML), "long html marked meaningful")
assert_(not rh.has_meaningful_answer(SHORT_HTML), "short html NOT meaningful")
assert_(not rh.has_meaningful_answer(""), "empty html NOT meaningful")
assert_(not rh.has_meaningful_answer(None), "None html NOT meaningful")
print("PASS  has_meaningful_answer threshold behaves  (4 assertions)")

# ────────────────────────────────────────────────────────────────────────────
# Section 2 — SSE session persistence (_build_done_payload calls session.save)
# ────────────────────────────────────────────────────────────────────────────

import inspect  # noqa: E402

src = inspect.getsource(chat_views._build_done_payload)
assert_(
    "request.session.save()" in src,
    "_build_done_payload must call request.session.save() explicitly",
)
# Belt-and-braces: the modified flag is still set so callers that DO have a
# normal (non-streaming) request flush correctly via SessionMiddleware.
assert_("request.session.modified = True" in src, "session.modified still set")
# And the explicit save is wrapped in a try/except so a session-store hiccup
# never crashes the SSE done frame after the bubble already rendered.
assert_("except Exception" in src and "logger.exception" in src, "session.save wrapped in try/except")
print("PASS  _build_done_payload persists session explicitly  (3 assertions)")

# Behavioural test using Django's test client. We hit /stream/ directly,
# walk the SSE stream to its done frame, then issue a second GET to /chat/
# and confirm the conversation row is in the sidebar.
from django.test import Client  # noqa: E402
from unittest.mock import patch  # noqa: E402

DEMO_PASSWORD = os.environ["DEMO_PASSWORD"]

# Synthetic pipeline result: long enough markdown that has_meaningful_answer
# is True and the answer survives sanitisation.
fake_answer = "# Stub answer\n\n" + "\n".join(f"- bullet {i}" for i in range(20))


def _fake_run_query_streaming(**kw):
    # Emit no progress events; just return a result holder mirroring the real
    # manager's shape.
    return {
        "final_answer":  fake_answer,
        "active_agents": ["researcher"],
        "errors":        [],
        "research_results": [],
        "structured_data":  [],
    }


client = Client()
# Authenticate via the demo password endpoint.
resp = client.post("/login/", {"password": DEMO_PASSWORD}, follow=True)
assert_(resp.status_code == 200, "login OK")

with patch("chat.agents.manager.run_query_streaming", _fake_run_query_streaming):
    sse_resp = client.get("/stream/", {"query": "What is the win number for HD-104?"})
    assert_(sse_resp.status_code == 200, "/stream/ returns 200")
    # Drain the streaming response so the worker thread runs and the done
    # frame fires (and our explicit session.save() executes).
    chunks = b"".join(sse_resp.streaming_content)
    body = chunks.decode("utf-8")
    assert_('"type": "done"' in body or '"type":"done"' in body, "done frame emitted")

# Now hit /chat/ — the conversation should be in the sidebar.
chat_resp = client.get("/chat/")
assert_(chat_resp.status_code == 200, "/chat/ OK")
chat_body = html.unescape(chat_resp.content.decode("utf-8"))
assert_(
    "No conversations yet" not in chat_body,
    "sidebar should NOT show 'No conversations yet' after a streamed turn",
)
# The conversation title is auto-generated from the query — at least one of
# its content words should appear in the sidebar block.
sidebar_match = re.search(
    r'id="sidebar-conv-list".*?</div>',
    chat_body,
    re.DOTALL,
)
assert_(sidebar_match is not None, "sidebar block found")
sidebar_html = sidebar_match.group(0).lower()
assert_(
    "win" in sidebar_html or "hd-104" in sidebar_html or "number" in sidebar_html,
    "sidebar should include the conversation title from the streamed turn",
)
print("PASS  streamed turn persists into session sidebar  (6 assertions)")

# ────────────────────────────────────────────────────────────────────────────
# Section 3 — translations wired up for toggle strings
# ────────────────────────────────────────────────────────────────────────────

chat_html = (PROJECT_DIR / "templates" / "chat.html").read_text(encoding="utf-8")

# Every toggle string is wrapped in a {% trans %} call.
required_trans_in_template = [
    'trans "Theme"',
    'trans "System"',
    'trans "Light"',
    'trans "Dark"',
    'trans "A/B test variants"',
    'trans \'A/B test toggle\'',
    'trans "Off (single variant per format)."',
    'trans "Mode"',
    'trans "Auto"',
    'trans "Mobilization"',
    'trans "Persuasion"',
    'trans "Auto picks the mix."',
]
for needle in required_trans_in_template:
    assert_(needle in chat_html, f"chat.html must contain `{{% {needle} %}}`")
print(f"PASS  toggle strings wrapped in trans tags  ({len(required_trans_in_template)} assertions)")

# Hardcoded English strings that JS used to set on toggle hints must be gone.
forbidden = [
    "'Auto picks the mix.'",
    "'GOTV your supporters.'",
    "'Move undecided voters.'",
]
# These appear in {% trans 'Auto picks the mix.' %} (single quoted) but should
# NOT appear as bare JS string literals like   HINTS = { auto: 'Auto picks...'
# Look for the old constant name to be sure it's gone.
assert_("HINTS = {" not in chat_html, "old hardcoded HINTS literal removed from JS")
print("PASS  hardcoded English HINTS literal removed from JS  (1 assertion)")

# .po + .mo files have actual translations for every required msgid.
required_strings = [
    "Theme", "System", "Light", "Dark",
    "Follow your device setting", "Always light", "Always dark",
    "A/B test toggle", "A/B test variants",
    "Generate two variants of every social messaging output",
    "Off (single variant per format).",
    "On: two variants per social format + sample-size math.",
    "Plan mode", "Mode", "Auto", "Mobilization", "Persuasion",
    "Let Powerbuilder pick the natural mix",
    "GOTV: speak to supporters who already agree",
    "Move undecided or soft-opposing voters",
    "Auto picks the mix.", "GOTV your supporters.", "Move undecided voters.",
]


def _msgstr_for(po_text: str, msgid: str) -> str | None:
    """Return the msgstr that follows `msgid "<msgid>"`. None if not found."""
    pattern = re.compile(
        r'msgid "' + re.escape(msgid.replace("\\", "\\\\").replace('"', '\\"'))
        + r'"\nmsgstr "([^"\n]*)"'
    )
    m = pattern.search(po_text)
    return m.group(1) if m else None


for locale in ("es", "vi"):
    po_path = PROJECT_DIR / "locale" / locale / "LC_MESSAGES" / "django.po"
    po_text = po_path.read_text(encoding="utf-8")
    for s in required_strings:
        msgstr = _msgstr_for(po_text, s)
        assert_(msgstr is not None, f"{locale}: msgid {s!r} missing")
        assert_(msgstr not in (None, ""), f"{locale}: msgid {s!r} has empty msgstr")
    # The .mo MUST exist and be more than a stub.
    mo_path = PROJECT_DIR / "locale" / locale / "LC_MESSAGES" / "django.mo"
    assert_(mo_path.exists(), f"{locale}: django.mo must exist")
    assert_(mo_path.stat().st_size > 1024, f"{locale}: django.mo non-trivial size")
print(f"PASS  ES + VI .po/.mo carry translations for every toggle string  ({(len(required_strings)*2 + 4)} assertions)")

# Translation actually flips through gettext.
from django.utils import translation as dj_trans  # noqa: E402

with dj_trans.override("es"):
    assert_(dj_trans.gettext("Theme") == "Tema", "ES: Theme → Tema")
    assert_(dj_trans.gettext("Auto picks the mix.") == "Auto elige la mezcla.", "ES: hint")
with dj_trans.override("vi"):
    assert_(dj_trans.gettext("Theme") == "Giao diện", "VI: Theme → Giao diện")
    assert_(dj_trans.gettext("Mobilization") == "Huy động", "VI: Mobilization")
print("PASS  gettext returns translated strings under ES + VI overrides  (4 assertions)")

# Final tally
print(f"\nALL PASS — {assertions} assertions")
