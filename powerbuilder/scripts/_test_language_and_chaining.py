"""
Smoke tests for:
  (A) Language detection in chat/agents/manager.py:_detect_language_intent
  (B) Chaining safety guard:
      MESSAGING router decision is rewritten to RESEARCHER when
      research_results is empty.
  (C) Prompt construction in chat/agents/messaging.py emits a
      LANGUAGE DIRECTIVE block when language_intent is non-English.

These run without needing real LLM keys: we monkey-patch the LLM client.
"""

import os
import sys
import django

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "powerbuilder_app.settings")
django.setup()

from chat.agents.manager import _detect_language_intent, intent_router_node
from chat.agents import messaging as msg_mod

# -------------------------------------------------------------------
# (A) Language detection
# -------------------------------------------------------------------
print("=== (A) Language detection ===")
cases = [
    ("Spanish door knock script for Latinx voters 18-35 in Gwinnett", "es"),
    ("Generate a canvassing script in Spanish",                       "es"),
    ("Necesito un script en espa\u00f1ol",                              "es"),
    ("Mandarin phone script for Asian voters in GA-07",              "zh"),
    ("Vietnamese mail piece",                                         "vi"),
    ("Korean text messages",                                          "ko"),
    ("English door knock script",                                     "en"),
    ("Door knock script for Gwinnett",                                "en"),
]
fails = 0
for q, expected in cases:
    got = _detect_language_intent(q)
    ok = "OK " if got == expected else "FAIL"
    if got != expected:
        fails += 1
    print(f"  {ok}  expected={expected:<3} got={got:<3}  query={q!r}")
print()

# -------------------------------------------------------------------
# (B) Chaining safety guard \u2014 simulate LLM picking MESSAGING with empty
# research_results. The router must rewrite to researcher.
# -------------------------------------------------------------------
print("=== (B) Chaining safety guard ===")

# Monkey-patch get_model so we don't make a real LLM call. Force it to
# always return "DECISION: MESSAGING, FORMAT: MARKDOWN".
class _FakeResp:
    content = "DECISION: MESSAGING, FORMAT: MARKDOWN"

class _FakeLLM:
    def invoke(self, prompt):
        return _FakeResp()

import chat.agents.manager as mgr
mgr.get_model = lambda: _FakeLLM()

# Case 1: empty research_results, no researcher run \u2192 should rewrite to researcher
state1 = {
    "query": "give me a door knock script in Spanish",  # triggers language detection
    "active_agents": [],
    "research_results": [],
    "structured_data": [],
}
out1 = intent_router_node(state1)
ok1 = out1["router_decision"] == "researcher"
print(f"  {'OK ' if ok1 else 'FAIL'}  empty research_results \u2192 decision={out1['router_decision']} (expected researcher)")
print(f"        language_intent={out1.get('language_intent')} (expected es)")

# Case 2: research_results populated, LLM picks messaging \u2192 should keep messaging
state2 = {
    "query": "now generate the messaging in Spanish",
    "active_agents": ["researcher"],
    "research_results": ["--- MEMO FROM SOURCE: x | DATE: 2026-01-01 ---\nfindings here\n"],
    "structured_data": [],
}
out2 = intent_router_node(state2)
ok2 = out2["router_decision"] == "messaging"
print(f"  {'OK ' if ok2 else 'FAIL'}  research_results populated \u2192 decision={out2['router_decision']} (expected messaging)")
print(f"        language_intent={out2.get('language_intent')} (expected es)")
print()

# -------------------------------------------------------------------
# (C) Prompt construction in messaging_node \u2014 capture the prompt that
# would be sent to the LLM and assert it contains the language directive
# when language_intent='es'.
# -------------------------------------------------------------------
print("=== (C) Messaging prompt contains LANGUAGE DIRECTIVE for es ===")

captured = {}

class _CapturingLLM:
    def invoke(self, prompt):
        captured["prompt"] = prompt
        # Return a minimal valid response with all section markers so the
        # parser exits cleanly and the function returns successfully.
        return _CapturedResp()

class _CapturedResp:
    content = "\n".join([
        "===CANVASSING_SCRIPT===",
        "Hola, soy Maria con la campa\u00f1a.",
        "===PHONE_SCRIPT===",
        "Hola, le llamo de la campa\u00f1a.",
        "===TEXT_SCRIPT===",
        "Hola [NAME], vote el 3 de noviembre.",
        "===MAIL_NARRATIVE===",
        "Estimado/a votante, su voto cuenta...",
        "===DIGITAL_COPY===",
        "Variaci\u00f3n A: Vote el 3 de noviembre.",
    ])

msg_mod.get_completion_client = lambda temperature=0.4: _CapturingLLM()

# Build a minimal state that the messaging_node will accept.
state_msg = {
    "query": "Spanish door script",
    "research_results": ["--- MEMO FROM SOURCE: Acme | DATE: 2026-01-15 ---\nIssue: housing costs are top-of-mind for renters in Gwinnett.\n"],
    "structured_data": [],
    "language_intent": "es",
}
result = msg_mod.messaging_node(state_msg)
prompt_text = captured.get("prompt", "")

checks = [
    ("LANGUAGE DIRECTIVE present", "LANGUAGE DIRECTIVE" in prompt_text),
    ("WRITE ALL FIVE ... IN SPANISH", "WRITE ALL FIVE MESSAGING SECTIONS IN SPANISH" in prompt_text),
    ("Style hint present (t\u00fa-form)", "t\u00fa-form" in prompt_text),
    ("Markers preserved in prompt", "===CANVASSING_SCRIPT===" in prompt_text),
    ("messaging_node returned outputs", bool(result.get("research_results"))),
    ("Output header tags LANGUAGE: Spanish",
     any("LANGUAGE: Spanish" in line for line in (result.get("research_results") or []))),
]
for label, ok in checks:
    print(f"  {'OK ' if ok else 'FAIL'}  {label}")

# Negative control: language_intent='en' must NOT include the directive.
captured.clear()
state_en = dict(state_msg)
state_en["language_intent"] = "en"
result_en = msg_mod.messaging_node(state_en)
prompt_en = captured.get("prompt", "")
print(f"  {'OK ' if 'LANGUAGE DIRECTIVE' not in prompt_en else 'FAIL'}  English prompt OMITS LANGUAGE DIRECTIVE")
print(f"  {'OK ' if not any('LANGUAGE:' in line for line in (result_en.get('research_results') or [])) else 'FAIL'}  English output OMITS language tag in header")

print()
if fails or not all(c[1] for c in checks):
    print("SOME TESTS FAILED")
    sys.exit(1)
print("ALL TESTS PASSED")
