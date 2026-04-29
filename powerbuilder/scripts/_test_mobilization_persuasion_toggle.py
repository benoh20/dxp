"""
Milestone L: Mobilization vs Persuasion plan-mode toggle.

Coverage:
  (A) PLAN_MODES tuple, MODE_LABELS, MODE_DESCRIPTIONS, MODE_CTA_HINTS shape.
  (B) Defensive normalization for both _normalize_plan_mode helpers
      (messaging.py and manager.py).
  (C) _build_mode_directive: empty for auto, non-empty + correct keywords
      for mobilization and persuasion.
  (D) _build_mode_cta_block: empty for auto, every format key present for
      mobilization and persuasion.
  (E) _detect_plan_mode in manager.py: explicit override wins, keyword
      fallback works, returns "auto" otherwise.
  (F) intent_router_node threads plan_mode through every return path.
  (G) messaging_node prompt assembly: AUTO mode produces no STRATEGIC FRAME
      block; MOBILIZATION and PERSUASION inject the matching directive +
      per-format CTA hints; output headers carry MODE tag for non-auto.
  (H) views surface check: send_message_view + stream_query_view read
      'plan_mode' from request and pass it through to run_query helpers.
  (I) Template wiring: chat.html exposes the segmented toggle, hidden
      input, and SSE URL adds plan_mode when non-auto.
  (J) End-to-end through run_query (manager monkey-patched) shows the
      override flowing into messaging_node state.

Tests follow the existing house pattern: PASS lines per section + final
assertion count printed.
"""

import os
import sys
import django

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "powerbuilder_app.settings")
django.setup()

# pylint: disable=wrong-import-position
from chat.agents import messaging as msg_mod
import chat.agents.manager as mgr_mod
from chat.agents.manager import (
    _detect_plan_mode,
    _normalize_plan_mode as _norm_mgr,
    intent_router_node,
)


_assert_count = 0


def assert_(cond, msg):
    global _assert_count
    _assert_count += 1
    if not cond:
        print(f"FAIL: {msg}")
        sys.exit(1)


# ---------------------------------------------------------------------------
# (A) Constants surface area
# ---------------------------------------------------------------------------
print("=== (A) Constants ===")
assert_(msg_mod.PLAN_MODES == ("auto", "mobilization", "persuasion"),
        "PLAN_MODES tuple wrong")
assert_(set(msg_mod.MODE_LABELS) == {"auto", "mobilization", "persuasion"},
        "MODE_LABELS keys wrong")
assert_(msg_mod.MODE_LABELS["mobilization"] == "Mobilization",
        "MOBILIZATION label wrong")
assert_(msg_mod.MODE_LABELS["persuasion"] == "Persuasion",
        "PERSUASION label wrong")
assert_(set(msg_mod.MODE_DESCRIPTIONS) == {"auto", "mobilization", "persuasion"},
        "MODE_DESCRIPTIONS keys wrong")
# Descriptions must mention the right strategic frame keywords.
assert_("MOBILIZATION MODE" in msg_mod.MODE_DESCRIPTIONS["mobilization"],
        "mobilization description missing header")
assert_("PERSUASION MODE" in msg_mod.MODE_DESCRIPTIONS["persuasion"],
        "persuasion description missing header")
assert_("ID-as-noun" in msg_mod.MODE_DESCRIPTIONS["mobilization"],
        "mobilization description missing ID-as-noun framing")
assert_("Coppock" in msg_mod.MODE_DESCRIPTIONS["persuasion"],
        "persuasion description missing Coppock citation")
# Per-format CTA hints — both non-auto modes cover all eight FORMAT_LABELS keys.
EXPECTED_FORMATS = {
    "canvassing_script", "phone_script", "text_script", "mail_narrative",
    "digital_copy", "meta_post", "youtube_script", "tiktok_script",
}
assert_(set(msg_mod.MODE_CTA_HINTS["mobilization"]) == EXPECTED_FORMATS,
        "MOBILIZATION CTA hints missing format keys")
assert_(set(msg_mod.MODE_CTA_HINTS["persuasion"]) == EXPECTED_FORMATS,
        "PERSUASION CTA hints missing format keys")
assert_(msg_mod.MODE_CTA_HINTS["auto"] == {}, "AUTO must have empty CTA hints")
print(f"PASS section A (constants): {_assert_count} checks")

# ---------------------------------------------------------------------------
# (B) Defensive normalization
# ---------------------------------------------------------------------------
print("=== (B) _normalize_plan_mode (both copies) ===")
prev = _assert_count
for fn, name in ((msg_mod._normalize_plan_mode, "messaging"),
                 (_norm_mgr, "manager")):
    assert_(fn(None)            == "auto", f"{name}: None -> auto")
    assert_(fn("")              == "auto", f"{name}: '' -> auto")
    assert_(fn("AUTO")          == "auto", f"{name}: AUTO -> auto")
    assert_(fn(" Mobilization ") == "mobilization", f"{name}: trim+lower")
    assert_(fn("persuasion")    == "persuasion", f"{name}: persuasion ok")
    assert_(fn("garbage")       == "auto", f"{name}: unknown -> auto")
    assert_(fn(123)             == "auto", f"{name}: non-str -> auto")
    assert_(fn([])              == "auto", f"{name}: list -> auto")
print(f"PASS section B (normalize): {_assert_count - prev} checks")

# ---------------------------------------------------------------------------
# (C) _build_mode_directive
# ---------------------------------------------------------------------------
print("=== (C) _build_mode_directive ===")
prev = _assert_count
assert_(msg_mod._build_mode_directive("auto") == "",
        "auto must return empty directive")
assert_(msg_mod._build_mode_directive(None) == "",
        "None must return empty directive (auto fallback)")
mob = msg_mod._build_mode_directive("mobilization")
pers = msg_mod._build_mode_directive("persuasion")
assert_("STRATEGIC FRAME" in mob, "mobilization directive missing header")
assert_("MOBILIZATION MODE" in mob, "mobilization directive missing body")
assert_("STRATEGIC FRAME" in pers, "persuasion directive missing header")
assert_("PERSUASION MODE" in pers, "persuasion directive missing body")
# Mobilization should NOT mention persuasion-specific framing language.
assert_("PERSUASION MODE" not in mob,
        "mobilization directive contaminated with persuasion text")
assert_("MOBILIZATION MODE" not in pers,
        "persuasion directive contaminated with mobilization text")
print(f"PASS section C (directive): {_assert_count - prev} checks")

# ---------------------------------------------------------------------------
# (D) _build_mode_cta_block
# ---------------------------------------------------------------------------
print("=== (D) _build_mode_cta_block ===")
prev = _assert_count
assert_(msg_mod._build_mode_cta_block("auto") == "",
        "auto must return empty CTA block")
mob_cta = msg_mod._build_mode_cta_block("mobilization")
pers_cta = msg_mod._build_mode_cta_block("persuasion")
assert_("PER-FORMAT CTA SHAPE (MOBILIZATION)" in mob_cta,
        "mobilization CTA block header missing")
assert_("PER-FORMAT CTA SHAPE (PERSUASION)" in pers_cta,
        "persuasion CTA block header missing")
for fmt in EXPECTED_FORMATS:
    assert_(fmt in mob_cta, f"mobilization CTA block missing {fmt}")
    assert_(fmt in pers_cta, f"persuasion CTA block missing {fmt}")
print(f"PASS section D (cta block): {_assert_count - prev} checks")

# ---------------------------------------------------------------------------
# (E) _detect_plan_mode in manager.py
# ---------------------------------------------------------------------------
print("=== (E) _detect_plan_mode ===")
prev = _assert_count
# Explicit override wins over query keywords
assert_(_detect_plan_mode("just a generic query", "mobilization") == "mobilization",
        "explicit override mobilization not honored")
assert_(_detect_plan_mode("turnout the base", "persuasion") == "persuasion",
        "explicit override persuasion must beat keyword fallback")
# Garbage override falls through to keyword detection
assert_(_detect_plan_mode("GOTV plan for Gwinnett", "garbage") == "mobilization",
        "garbage override should not block keyword detection")
# Keyword fallback
assert_(_detect_plan_mode("Persuade undecided voters in GA-06") == "persuasion",
        "keyword fallback persuasion")
assert_(_detect_plan_mode("Build a turnout plan for our supporters") == "mobilization",
        "keyword fallback mobilization")
assert_(_detect_plan_mode("Door knock script for Gwinnett") == "auto",
        "neutral query must default to auto")
assert_(_detect_plan_mode("") == "auto", "empty query -> auto")
assert_(_detect_plan_mode(None) == "auto", "None query -> auto")
print(f"PASS section E (detect plan mode): {_assert_count - prev} checks")

# ---------------------------------------------------------------------------
# (F) intent_router_node threads plan_mode through every return path
# ---------------------------------------------------------------------------
print("=== (F) Router threading ===")
prev = _assert_count


class _FakeResp:
    content = "DECISION: MESSAGING, FORMAT: MARKDOWN"


class _FakeLLM:
    def invoke(self, prompt):
        return _FakeResp()


# Force the LLM-routed path to be deterministic.
mgr_mod.get_model = lambda: _FakeLLM()

# Path 1: voter_file fast path (file present, voter_file keywords).
out_vf = intent_router_node({
    "query": "Use my voter file to build target list",
    "uploaded_file_path": "/tmp/dummy.csv",
    "active_agents": [],
    "research_results": [],
    "structured_data": [],
    "plan_mode": "mobilization",
})
assert_(out_vf["router_decision"] == "voter_file",
        "voter_file fast path decision wrong")
assert_(out_vf["plan_mode"] == "mobilization",
        "voter_file path lost plan_mode override")

# Path 2: opposition research fast path -> election_results first.
out_opp = intent_router_node({
    "query": "Pull opposition research on the Republican candidate",
    "active_agents": [],
    "research_results": [],
    "structured_data": [],
    "plan_mode": "persuasion",
})
assert_(out_opp["router_decision"] == "election_results",
        "opp fast path should send to election_results first")
assert_(out_opp["plan_mode"] == "persuasion",
        "opp election_results path lost plan_mode")

# Path 3: opposition research after election_results ran.
out_opp2 = intent_router_node({
    "query": "Pull opposition research on the Republican candidate",
    "active_agents": ["election_results"],
    "research_results": [],
    "structured_data": [],
    "plan_mode": "persuasion",
})
assert_(out_opp2["router_decision"] == "opposition_research",
        "opp second hop wrong")
assert_(out_opp2["plan_mode"] == "persuasion",
        "opp opposition_research path lost plan_mode")

# Path 4: voter_file sequence after voterfile already ran (no district).
out_seq = intent_router_node({
    "query": "Use my voter file (no district reference)",
    "active_agents": ["voter_file"],
    "research_results": [],
    "structured_data": [],
    "plan_mode": "mobilization",
})
assert_(out_seq["router_decision"] == "researcher",
        "voter_file sequence should route to researcher next")
assert_(out_seq["plan_mode"] == "mobilization",
        "voter_file sequence lost plan_mode")

# Path 5: full LLM-decided path (no fast path matches), with override.
out_llm = intent_router_node({
    "query": "Door-knock script for Gwinnett",
    "active_agents": ["researcher"],
    "research_results": ["--- MEMO ---\nfindings\n"],
    "structured_data": [],
    "plan_mode": "persuasion",
})
assert_(out_llm["plan_mode"] == "persuasion",
        "LLM-decided router path lost plan_mode")
assert_("router_decision" in out_llm, "router missing decision key")

# Path 6: keyword fallback with no explicit override
out_kw = intent_router_node({
    "query": "Build a GOTV plan for our supporters in Gwinnett",
    "active_agents": ["researcher"],
    "research_results": ["--- MEMO ---\nfindings\n"],
    "structured_data": [],
    # No plan_mode in state -> should detect via keywords
})
assert_(out_kw["plan_mode"] == "mobilization",
        "router keyword fallback should detect mobilization")

print(f"PASS section F (router threading): {_assert_count - prev} checks")

# ---------------------------------------------------------------------------
# (G) messaging_node prompt assembly + output header tagging
# ---------------------------------------------------------------------------
print("=== (G) Messaging prompt + output header ===")
prev = _assert_count

captured = {}


class _CapturingLLM:
    def invoke(self, prompt):
        captured["prompt"] = prompt
        return _CapturedResp()


class _CapturedResp:
    content = "\n".join([
        "===CANVASSING_SCRIPT===",
        "Hi, I'm Maria with the campaign.",
        "===PHONE_SCRIPT===",
        "Hi, calling from the campaign.",
        "===TEXT_SCRIPT===",
        "Hi NAME, vote on Nov 5.",
        "===MAIL_NARRATIVE===",
        "Dear voter, your vote counts.",
        "===DIGITAL_COPY===",
        "Vote on Nov 5.",
        "===META_POST===",
        "Vote on Nov 5.",
        "===YOUTUBE_SCRIPT===",
        "Hook at 0:00.",
        "===TIKTOK_SCRIPT===",
        "Hook 15s.",
    ])


msg_mod.get_completion_client = lambda temperature=0.4: _CapturingLLM()


def _run_messaging(plan_mode_value):
    captured.clear()
    state = {
        "query": "Door knock script for Gwinnett",
        "research_results": [
            "--- MEMO FROM SOURCE: Acme | DATE: 2026-01-15 ---\n"
            "Issue: housing costs are top-of-mind for renters in Gwinnett.\n"
        ],
        "structured_data": [],
        "language_intent": "en",
        "plan_mode": plan_mode_value,
    }
    return msg_mod.messaging_node(state), captured.get("prompt", "")


# Auto mode -> no STRATEGIC FRAME, no PER-FORMAT CTA SHAPE
res_auto, prompt_auto = _run_messaging("auto")
assert_("STRATEGIC FRAME" not in prompt_auto,
        "auto prompt must not contain STRATEGIC FRAME")
assert_("PER-FORMAT CTA SHAPE" not in prompt_auto,
        "auto prompt must not contain PER-FORMAT CTA SHAPE")
assert_(bool(res_auto.get("research_results")),
        "auto messaging_node returned no outputs")
# No mode tag in output headers when auto
assert_(not any("MODE:" in chunk for chunk in res_auto["research_results"]),
        "auto outputs must not carry MODE tag")

# Mobilization mode -> directive + CTA block injected
res_mob, prompt_mob = _run_messaging("mobilization")
assert_("STRATEGIC FRAME" in prompt_mob,
        "mobilization prompt missing STRATEGIC FRAME header")
assert_("MOBILIZATION MODE" in prompt_mob,
        "mobilization prompt missing description body")
assert_("PER-FORMAT CTA SHAPE (MOBILIZATION)" in prompt_mob,
        "mobilization prompt missing per-format CTA block")
assert_("ID-as-noun" in prompt_mob,
        "mobilization prompt missing ID-as-noun reference")
assert_("PERSUASION MODE" not in prompt_mob,
        "mobilization prompt contaminated with persuasion text")
# Output header must include MODE tag.
assert_(any("MODE: Mobilization" in chunk for chunk in res_mob["research_results"]),
        "mobilization outputs missing MODE tag in header")

# Persuasion mode -> different directive
res_pers, prompt_pers = _run_messaging("persuasion")
assert_("PERSUASION MODE" in prompt_pers,
        "persuasion prompt missing description body")
assert_("PER-FORMAT CTA SHAPE (PERSUASION)" in prompt_pers,
        "persuasion prompt missing per-format CTA block")
assert_("Coppock" in prompt_pers,
        "persuasion prompt missing Coppock citation")
assert_("MOBILIZATION MODE" not in prompt_pers,
        "persuasion prompt contaminated with mobilization text")
assert_(any("MODE: Persuasion" in chunk for chunk in res_pers["research_results"]),
        "persuasion outputs missing MODE tag in header")

# Garbage mode -> normalizes to auto, prompt is byte-identical to auto path
res_bad, prompt_bad = _run_messaging("garbage_value")
assert_("STRATEGIC FRAME" not in prompt_bad,
        "garbage mode should normalize to auto and skip STRATEGIC FRAME")
print(f"PASS section G (messaging prompt): {_assert_count - prev} checks")

# ---------------------------------------------------------------------------
# (H) Views surface check
# ---------------------------------------------------------------------------
print("=== (H) Views thread plan_mode through ===")
prev = _assert_count

views_src = open(os.path.join(ROOT, "chat", "views.py"), "r", encoding="utf-8").read()
assert_('request.POST.get("plan_mode"' in views_src,
        "send_message_view must read plan_mode from POST")
assert_('request.GET.get("plan_mode"' in views_src,
        "stream_query_view must read plan_mode from GET")
assert_("plan_mode        = plan_mode" in views_src
        or "plan_mode=plan_mode" in views_src
        or "plan_mode          = plan_mode" in views_src,
        "views must pass plan_mode kwarg into run_query / run_query_streaming")

# Manager run_query helpers accept plan_mode kwarg
import inspect
sig_run = inspect.signature(mgr_mod.run_query)
sig_stream = inspect.signature(mgr_mod.run_query_streaming)
assert_("plan_mode" in sig_run.parameters,
        "run_query must accept plan_mode kwarg")
assert_("plan_mode" in sig_stream.parameters,
        "run_query_streaming must accept plan_mode kwarg")
print(f"PASS section H (views): {_assert_count - prev} checks")

# ---------------------------------------------------------------------------
# (I) Template wiring
# ---------------------------------------------------------------------------
print("=== (I) Template + JS wiring ===")
prev = _assert_count

import html as html_mod
tpl_src_raw = open(os.path.join(ROOT, "templates", "chat.html"), "r", encoding="utf-8").read()
tpl_src = html_mod.unescape(tpl_src_raw)

# Hidden input + segmented buttons present
assert_('id="plan-mode-input"' in tpl_src,
        "hidden plan_mode input missing")
assert_('name="plan_mode"' in tpl_src,
        "hidden input must have name=plan_mode for the form POST")
assert_('id="mode-toggle-group"' in tpl_src,
        "mode toggle group container missing")
for mode_label in ("Auto", "Mobilization", "Persuasion"):
    assert_(f'>{mode_label}<' in tpl_src,
            f"toggle button {mode_label} missing from template")
for mode_value in ("auto", "mobilization", "persuasion"):
    assert_(f'data-mode="{mode_value}"' in tpl_src,
            f"toggle button data-mode={mode_value} missing")

# Auto must default to aria-pressed=true; the others must default to false.
assert_('data-mode="auto" aria-pressed="true"' in tpl_src,
        "auto button must default aria-pressed=true")
assert_('data-mode="mobilization" aria-pressed="false"' in tpl_src,
        "mobilization button must default aria-pressed=false")
assert_('data-mode="persuasion" aria-pressed="false"' in tpl_src,
        "persuasion button must default aria-pressed=false")

# JS wires the SSE URL to include plan_mode when non-auto
assert_("plan_mode=" in tpl_src,
        "SSE URL must append plan_mode when non-auto")
assert_("getPlanMode()" in tpl_src,
        "form submit must call getPlanMode() when starting stream")

# CSS hooks
assert_(".mode-toggle__btn[aria-pressed=\"true\"]" in tpl_src,
        "active-state CSS rule for toggle button missing")
print(f"PASS section I (template): {_assert_count - prev} checks")

# ---------------------------------------------------------------------------
# (J) End-to-end: run_query passes plan_mode into initial state
# ---------------------------------------------------------------------------
print("=== (J) run_query end-to-end plumbing ===")
prev = _assert_count

# Stub manager_app.invoke to capture initial_state without running the graph.
captured_state = {}


class _StubGraph:
    def invoke(self, initial_state, config=None):
        captured_state.update(initial_state)
        return {
            "final_answer": "ok",
            "active_agents": [],
            "errors": [],
        }


_orig_app = mgr_mod.manager_app
mgr_mod.manager_app = _StubGraph()
try:
    mgr_mod.run_query(
        query="GOTV plan for Gwinnett",
        org_namespace="general",
        plan_mode="mobilization",
    )
    assert_(captured_state.get("plan_mode") == "mobilization",
            "run_query must propagate plan_mode into initial state")

    captured_state.clear()
    mgr_mod.run_query(
        query="generic query",
        org_namespace="general",
        plan_mode="garbage_string",
    )
    assert_(captured_state.get("plan_mode") == "auto",
            "run_query must normalize unknown plan_mode -> auto")

    captured_state.clear()
    mgr_mod.run_query_streaming(
        query="persuasion plan",
        org_namespace="general",
        run_id="test-run-1",
        plan_mode="persuasion",
    )
    assert_(captured_state.get("plan_mode") == "persuasion",
            "run_query_streaming must propagate plan_mode")
    assert_(captured_state.get("run_id") == "test-run-1",
            "run_query_streaming must still set run_id alongside plan_mode")
finally:
    mgr_mod.manager_app = _orig_app

print(f"PASS section J (run_query e2e): {_assert_count - prev} checks")

# ---------------------------------------------------------------------------
print()
print(f"ALL PASS \u2014 _test_mobilization_persuasion_toggle.py ran {_assert_count} assertions")
