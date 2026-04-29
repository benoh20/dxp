"""
Milestone K: A/B scaffolding (variant generation + sample-size math).

Coverage:
  (A) Module surface area: AB_ELIGIBLE_FORMATS, defaults, public helpers.
  (B) _normalize_ab_test: defensive coercion from POST/state values.
  (C) compute_sample_size: known-good values from standard online A/B
      calculators across multiple baseline + MDE pairs, plus monotonicity
      properties (smaller MDE -> bigger n; lower power -> smaller n).
  (D) compute_total_messages.
  (E) split_variants: clean parse, missing markers, missing axis line.
  (F) format_ab_math_block: includes per-variant + total counts and the
      Coppock 2024 grounding citation in plain language.
  (G) is_ab_eligible: text/digital/meta/youtube/tiktok yes; canvassing
      and phone and mail no.
  (H) Router threading: ab_test propagates through every intent_router
      return path.
  (I) Messaging prompt: AB_PROMPT_INSTRUCTION block injected only when
      ab_test=True; absent when False.
  (J) Messaging output formatting: when ab_test=True, eligible formats
      get **Variant A** / **Variant B** Markdown headers and the math
      block is prepended exactly once. Non-eligible formats stay
      single-version.
  (K) Views thread ab_test through send_message_view + stream_query_view.
  (L) run_query / run_query_streaming accept ab_test kwarg and propagate
      it into initial state.
  (M) Template wiring: A/B chip + hidden input present, SSE URL appends
      ab_test=1 when toggled.
"""

import os
import sys
import math
import django

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "powerbuilder_app.settings")
django.setup()

# pylint: disable=wrong-import-position
from chat.agents import ab_scaffolding as ab
from chat.agents import messaging as msg_mod
import chat.agents.manager as mgr_mod
from chat.agents.manager import intent_router_node


_assert_count = 0


def assert_(cond, msg):
    global _assert_count
    _assert_count += 1
    if not cond:
        print(f"FAIL: {msg}")
        sys.exit(1)


# ---------------------------------------------------------------------------
# (A) Module surface area
# ---------------------------------------------------------------------------
print("=== (A) ab_scaffolding surface ===")
assert_(set(ab.AB_ELIGIBLE_FORMATS) == {
    "text_script", "digital_copy", "meta_post", "youtube_script", "tiktok_script",
}, "AB_ELIGIBLE_FORMATS set wrong")
assert_(0.0 < ab.DEFAULT_BASELINE_RATE < 1.0, "DEFAULT_BASELINE_RATE out of range")
assert_(0.0 < ab.DEFAULT_MDE < 1.0, "DEFAULT_MDE out of range")
assert_(ab.NUM_VARIANTS == 2, "NUM_VARIANTS must be 2 in K")
assert_(callable(ab.compute_sample_size), "compute_sample_size missing")
assert_(callable(ab.format_ab_math_block), "format_ab_math_block missing")
assert_("A/B TEST MODE" in ab.AB_PROMPT_INSTRUCTION,
        "AB_PROMPT_INSTRUCTION header missing")
assert_(">>> VARIANT A <<<" in ab.AB_PROMPT_INSTRUCTION,
        "Variant A subsection marker missing from prompt instruction")
assert_(">>> VARIANT B <<<" in ab.AB_PROMPT_INSTRUCTION,
        "Variant B subsection marker missing from prompt instruction")
print(f"PASS section A: {_assert_count} checks")

# ---------------------------------------------------------------------------
# (B) Defensive normalization
# ---------------------------------------------------------------------------
print("=== (B) _normalize_ab_test ===")
prev = _assert_count
for truthy in (True, 1, 1.0, "1", "true", "TRUE", "yes", "On", " on "):
    assert_(ab._normalize_ab_test(truthy) is True,
            f"truthy {truthy!r} should normalize to True")
for falsy in (False, 0, 0.0, "", None, "garbage", "off", "no", [], {}, "0"):
    assert_(ab._normalize_ab_test(falsy) is False,
            f"falsy {falsy!r} should normalize to False")
print(f"PASS section B: {_assert_count - prev} checks")

# ---------------------------------------------------------------------------
# (C) compute_sample_size: known-good values + monotonicity
# ---------------------------------------------------------------------------
print("=== (C) compute_sample_size ===")
prev = _assert_count
# Standard reference: 5% baseline, 2pp MDE, alpha=0.05, power=0.80.
# Online A/B calculators (Optimizely, Evan Miller) give ~2,200 per arm.
n_5_2 = ab.compute_sample_size(0.05, 0.02)
assert_(2100 <= n_5_2 <= 2300,
        f"5%/2pp expected ~2200/arm, got {n_5_2}")
# 10%/2pp -> larger sample (variance higher near p=0.5)
n_10_2 = ab.compute_sample_size(0.10, 0.02)
assert_(3700 <= n_10_2 <= 4000,
        f"10%/2pp expected ~3800/arm, got {n_10_2}")
# 5%/1pp -> ~4x bigger because n scales 1/MDE^2
n_5_1 = ab.compute_sample_size(0.05, 0.01)
assert_(8000 <= n_5_1 <= 8500,
        f"5%/1pp expected ~8200/arm, got {n_5_1}")
# Monotonicity: smaller MDE -> bigger n
assert_(ab.compute_sample_size(0.05, 0.005) > n_5_1,
        "smaller MDE must yield bigger sample size")
# Monotonicity: lower power -> smaller n required
n_low_power = ab.compute_sample_size(0.05, 0.02, power=0.80)
n_high_power = ab.compute_sample_size(0.05, 0.02, power=0.90)
assert_(n_high_power > n_low_power,
        "higher power must require bigger sample size")
# Defensive: zero/negative MDE falls back to default
assert_(ab.compute_sample_size(0.05, 0) == ab.compute_sample_size(0.05, ab.DEFAULT_MDE),
        "zero MDE must fall back to default")
assert_(ab.compute_sample_size(0.05, -0.01) == ab.compute_sample_size(0.05, ab.DEFAULT_MDE),
        "negative MDE must fall back to default")
# Defensive: garbage baseline falls back
assert_(ab.compute_sample_size("garbage", 0.02) == ab.compute_sample_size(ab.DEFAULT_BASELINE_RATE, 0.02),
        "garbage baseline must fall back to default")
# Always >= 1
assert_(ab.compute_sample_size(0.5, 0.5) >= 1,
        "sample size must always be at least 1")
print(f"PASS section C: {_assert_count - prev} checks")

# ---------------------------------------------------------------------------
# (D) compute_total_messages
# ---------------------------------------------------------------------------
print("=== (D) compute_total_messages ===")
prev = _assert_count
assert_(ab.compute_total_messages(2200) == 4400,
        "2200 per arm * 2 = 4400 total")
assert_(ab.compute_total_messages(2200, 3) == 6600,
        "3 arms scaling")
assert_(ab.compute_total_messages(0) == 2, "min 1 per arm * 2")
print(f"PASS section D: {_assert_count - prev} checks")

# ---------------------------------------------------------------------------
# (E) split_variants
# ---------------------------------------------------------------------------
print("=== (E) split_variants ===")
prev = _assert_count
clean = (
    ">>> VARIANT A <<<\n"
    "Vote on Nov 5, neighbors are joining you.\n"
    ">>> VARIANT B <<<\n"
    "Be a voter on Nov 5.\n"
    "*Variant axis: framing (action vs identity).*"
)
parsed = ab.split_variants(clean)
assert_(parsed["A"].startswith("Vote on Nov 5"),
        f"Variant A body wrong: {parsed['A']!r}")
assert_(parsed["B"].startswith("Be a voter"),
        f"Variant B body wrong: {parsed['B']!r}")
assert_("Variant axis: framing" in parsed["axis"],
        "axis annotation not extracted")
# Axis line should not appear inside the B body anymore.
assert_("Variant axis" not in parsed["B"],
        "axis line leaked into Variant B body")
# Missing markers -> whole content under A.
no_markers = ab.split_variants("just a single version, no variants here.")
assert_(no_markers["A"] == "just a single version, no variants here.",
        "missing markers should keep content as A")
assert_(no_markers["B"] == "", "missing markers must yield empty B")
# Empty input -> all empty.
empty = ab.split_variants("")
assert_(empty["A"] == "" and empty["B"] == "" and empty["axis"] == "",
        "empty input must yield empty triple")
# Only A marker -> B empty.
only_a = ab.split_variants(">>> VARIANT A <<<\nfoo\n")
assert_(only_a["A"] == "foo", f"only-A path wrong: {only_a!r}")
assert_(only_a["B"] == "", "only-A path must keep B empty")
print(f"PASS section E: {_assert_count - prev} checks")

# ---------------------------------------------------------------------------
# (F) format_ab_math_block
# ---------------------------------------------------------------------------
print("=== (F) format_ab_math_block ===")
prev = _assert_count
block = ab.format_ab_math_block(0.05, 0.02)
assert_("A/B sample-size math" in block, "math block header missing")
assert_("Baseline conversion: 5.0%" in block,
        "baseline percent rendered wrong")
assert_("2.0 percentage points" in block,
        "MDE rendered wrong")
assert_("messages per variant" in block,
        "per-variant copy missing")
assert_("Coppock" in block,
        "Coppock 2024 citation missing in math block")
# A nonzero count appears in the rendered block
expected_n = ab.compute_sample_size(0.05, 0.02)
assert_(f"{expected_n:,}" in block,
        f"expected per-variant count {expected_n} not in block: {block!r}")
expected_total = expected_n * 2
assert_(f"{expected_total:,}" in block,
        f"expected total count {expected_total} not in block")
print(f"PASS section F: {_assert_count - prev} checks")

# ---------------------------------------------------------------------------
# (G) is_ab_eligible
# ---------------------------------------------------------------------------
print("=== (G) is_ab_eligible ===")
prev = _assert_count
for fmt in ("text_script", "digital_copy", "meta_post", "youtube_script", "tiktok_script"):
    assert_(ab.is_ab_eligible(fmt), f"{fmt} should be eligible")
for fmt in ("canvassing_script", "phone_script", "mail_narrative", "garbage"):
    assert_(not ab.is_ab_eligible(fmt), f"{fmt} must NOT be eligible")
print(f"PASS section G: {_assert_count - prev} checks")

# ---------------------------------------------------------------------------
# (H) Router threading
# ---------------------------------------------------------------------------
print("=== (H) Router threading ===")
prev = _assert_count


class _FakeResp:
    content = "DECISION: MESSAGING, FORMAT: MARKDOWN"


class _FakeLLM:
    def invoke(self, prompt):
        return _FakeResp()


mgr_mod.get_model = lambda: _FakeLLM()

# Voter-file fast path
out_vf = intent_router_node({
    "query": "Use my voter file to build target list",
    "uploaded_file_path": "/tmp/dummy.csv",
    "active_agents": [],
    "research_results": [],
    "structured_data": [],
    "ab_test": True,
})
assert_(out_vf["router_decision"] == "voter_file", "voter_file fast path missing")
assert_(out_vf["ab_test"] is True, "voter_file path lost ab_test=True")

# Opposition fast path -> election_results
out_opp = intent_router_node({
    "query": "Pull opposition research on the Republican candidate",
    "active_agents": [],
    "research_results": [],
    "structured_data": [],
    "ab_test": True,
})
assert_(out_opp["router_decision"] == "election_results", "opp first hop wrong")
assert_(out_opp["ab_test"] is True, "opp first hop lost ab_test")

# Voter-file sequence -> researcher
out_seq = intent_router_node({
    "query": "use my voter file (no district)",
    "active_agents": ["voter_file"],
    "research_results": [],
    "structured_data": [],
    "ab_test": True,
})
assert_(out_seq["ab_test"] is True, "voter_file sequence lost ab_test")

# LLM-decided path
out_llm = intent_router_node({
    "query": "Door-knock script for Gwinnett",
    "active_agents": ["researcher"],
    "research_results": ["--- MEMO ---\nfindings\n"],
    "structured_data": [],
    "ab_test": True,
})
assert_(out_llm["ab_test"] is True, "LLM path lost ab_test")

# Default unset -> False
out_default = intent_router_node({
    "query": "Door-knock script for Gwinnett",
    "active_agents": ["researcher"],
    "research_results": ["--- MEMO ---\nfindings\n"],
    "structured_data": [],
})
assert_(out_default["ab_test"] is False, "missing ab_test must default to False")
print(f"PASS section H: {_assert_count - prev} checks")

# ---------------------------------------------------------------------------
# (I)+(J) Messaging prompt and output formatting
# ---------------------------------------------------------------------------
print("=== (I)+(J) Messaging prompt + output ===")
prev = _assert_count

captured = {}


class _CapturingLLM:
    def invoke(self, prompt):
        captured["prompt"] = prompt
        return _CapturedAB() if captured.get("mode") == "ab" else _CapturedSingle()


class _CapturedSingle:
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


# Each eligible format returns variants A and B with explicit markers + axis.
class _CapturedAB:
    content = "\n".join([
        "===CANVASSING_SCRIPT===",
        "Hi, I'm Maria.",
        "===PHONE_SCRIPT===",
        "Phone version.",
        "===TEXT_SCRIPT===",
        ">>> VARIANT A <<<",
        "Hi NAME, vote on Nov 5.",
        ">>> VARIANT B <<<",
        "NAME, be a voter on Nov 5.",
        "*Variant axis: framing (action vs identity).*",
        "===MAIL_NARRATIVE===",
        "Mail body.",
        "===DIGITAL_COPY===",
        ">>> VARIANT A <<<",
        "Click here to vote.",
        ">>> VARIANT B <<<",
        "Pledge to vote.",
        "*Variant axis: CTA verb (Click vs Pledge).*",
        "===META_POST===",
        ">>> VARIANT A <<<",
        "Meta A copy.",
        ">>> VARIANT B <<<",
        "Meta B copy.",
        "*Variant axis: hook.*",
        "===YOUTUBE_SCRIPT===",
        ">>> VARIANT A <<<",
        "Hook at 0:00 deadline.",
        ">>> VARIANT B <<<",
        "Hook at 0:00 evidence.",
        "*Variant axis: hook framing.*",
        "===TIKTOK_SCRIPT===",
        ">>> VARIANT A <<<",
        "Open on action.",
        ">>> VARIANT B <<<",
        "Open on surprising claim.",
        "*Variant axis: opener.*",
    ])


msg_mod.get_completion_client = lambda temperature=0.4: _CapturingLLM()


def _run_messaging(ab_value, mode_label):
    captured.clear()
    captured["mode"] = mode_label
    state = {
        "query": "Door knock script for Gwinnett",
        "research_results": [
            "--- MEMO FROM SOURCE: Acme | DATE: 2026-01-15 ---\n"
            "Issue: housing costs are top-of-mind for renters in Gwinnett.\n"
        ],
        "structured_data": [],
        "language_intent": "en",
        "ab_test": ab_value,
    }
    return msg_mod.messaging_node(state), captured.get("prompt", "")


# ab_test=False -> no AB DIRECTIVE in prompt, no Variant headers in output
res_off, prompt_off = _run_messaging(False, "single")
assert_("A/B TEST DIRECTIVE" not in prompt_off,
        "ab_test=False must NOT inject A/B TEST DIRECTIVE")
assert_("A/B TEST MODE" not in prompt_off,
        "ab_test=False must NOT inject A/B TEST MODE instruction")
assert_(bool(res_off.get("research_results")), "off-mode must still produce outputs")
for chunk in res_off["research_results"]:
    assert_("Variant A" not in chunk and "Variant B" not in chunk,
            "off-mode outputs must not include Variant labels")
    assert_("A/B sample-size math" not in chunk,
            "off-mode outputs must not include math block")
    assert_("AB: on" not in chunk, "off-mode header must not tag AB: on")

# ab_test=True -> AB DIRECTIVE in prompt + Variant headers + math block once
res_on, prompt_on = _run_messaging(True, "ab")
assert_("A/B TEST DIRECTIVE" in prompt_on,
        "ab_test=True must inject A/B TEST DIRECTIVE")
assert_("A/B TEST MODE" in prompt_on,
        "ab_test=True must inject A/B TEST MODE instruction body")
assert_(">>> VARIANT A <<<" in prompt_on,
        "prompt must include the variant marker spec")

# Identify outputs by FORMAT_LABELS and check structure
outputs = res_on["research_results"]
text_chunks = [c for c in outputs if "TEXT SCRIPT" in c]
canv_chunks = [c for c in outputs if "CANVASSING SCRIPT" in c]
mail_chunks = [c for c in outputs if "MAIL NARRATIVE" in c]
assert_(len(text_chunks) == 1 and len(canv_chunks) == 1 and len(mail_chunks) == 1,
        "expected exactly one chunk per format")

text_chunk = text_chunks[0]
assert_("**Variant A**" in text_chunk and "**Variant B**" in text_chunk,
        "text_script (eligible) must show Variant A and Variant B headers")
assert_("Variant axis:" in text_chunk,
        "text_script must surface the variant axis annotation")
assert_("AB: on" in text_chunk, "ab_test=True header must tag AB: on")

canv_chunk = canv_chunks[0]
assert_("**Variant A**" not in canv_chunk and "**Variant B**" not in canv_chunk,
        "canvassing_script (NOT eligible) must NOT include Variant headers")

mail_chunk = mail_chunks[0]
assert_("**Variant A**" not in mail_chunk,
        "mail_narrative (NOT eligible) must NOT include Variant headers")

# Math block should appear EXACTLY ONCE across all outputs.
math_count = sum(1 for c in outputs if "A/B sample-size math" in c)
assert_(math_count == 1,
        f"math block must appear exactly once across outputs, saw {math_count}")
# And it should land on the FIRST eligible format. Our FORMAT_LABELS order is
# canvassing, phone, text, mail, digital, meta, youtube, tiktok — so the first
# eligible format is text_script.
assert_("A/B sample-size math" in text_chunk,
        "math block must be prepended to first eligible format (text_script)")
print(f"PASS section I+J: {_assert_count - prev} checks")

# ---------------------------------------------------------------------------
# (K) Views thread ab_test through
# ---------------------------------------------------------------------------
print("=== (K) Views ===")
prev = _assert_count
views_src = open(os.path.join(ROOT, "chat", "views.py"), "r", encoding="utf-8").read()
assert_('request.POST.get("ab_test"' in views_src,
        "send_message_view must read ab_test from POST")
assert_('request.GET.get("ab_test"' in views_src,
        "stream_query_view must read ab_test from GET")
import inspect
assert_("ab_test" in inspect.signature(mgr_mod.run_query).parameters,
        "run_query must accept ab_test kwarg")
assert_("ab_test" in inspect.signature(mgr_mod.run_query_streaming).parameters,
        "run_query_streaming must accept ab_test kwarg")
print(f"PASS section K: {_assert_count - prev} checks")

# ---------------------------------------------------------------------------
# (L) run_query end-to-end propagation
# ---------------------------------------------------------------------------
print("=== (L) run_query propagation ===")
prev = _assert_count

captured_state = {}


class _StubGraph:
    def invoke(self, initial_state, config=None):
        captured_state.update(initial_state)
        return {"final_answer": "ok", "active_agents": [], "errors": []}


_orig_app = mgr_mod.manager_app
mgr_mod.manager_app = _StubGraph()
try:
    mgr_mod.run_query(
        query="GOTV plan", org_namespace="general", ab_test=True,
    )
    assert_(captured_state.get("ab_test") is True,
            "run_query must propagate ab_test=True")

    captured_state.clear()
    mgr_mod.run_query(
        query="GOTV plan", org_namespace="general",
    )
    assert_(captured_state.get("ab_test") is False,
            "run_query default must be ab_test=False")

    captured_state.clear()
    mgr_mod.run_query_streaming(
        query="GOTV plan", org_namespace="general", run_id="test-1", ab_test=True,
    )
    assert_(captured_state.get("ab_test") is True,
            "run_query_streaming must propagate ab_test=True")
    assert_(captured_state.get("run_id") == "test-1",
            "run_query_streaming must still set run_id alongside ab_test")
finally:
    mgr_mod.manager_app = _orig_app
print(f"PASS section L: {_assert_count - prev} checks")

# ---------------------------------------------------------------------------
# (M) Template wiring
# ---------------------------------------------------------------------------
print("=== (M) Template wiring ===")
prev = _assert_count
import html as html_mod
tpl_raw = open(os.path.join(ROOT, "templates", "chat.html"), "r", encoding="utf-8").read()
tpl = html_mod.unescape(tpl_raw)

assert_('id="ab-test-input"' in tpl, "hidden ab_test input missing")
assert_('name="ab_test"' in tpl, "hidden input must have name=ab_test")
assert_('id="ab-toggle-chip"' in tpl, "A/B chip element missing")
assert_('aria-pressed="false"' in tpl,
        "A/B chip must default aria-pressed=false")
assert_("A/B test variants" in tpl, "A/B chip label text missing")
assert_("ab_test=1" in tpl,
        "SSE URL must append ab_test=1 when toggled")
assert_("getAbTest()" in tpl,
        "form submit must call getAbTest() when starting stream")
# CSS hooks
assert_(".ab-toggle__chip[aria-pressed=\"true\"]" in tpl,
        "active-state CSS rule for A/B chip missing")
print(f"PASS section M: {_assert_count - prev} checks")

# ---------------------------------------------------------------------------
print()
print(f"ALL PASS \u2014 _test_ab_scaffolding.py ran {_assert_count} assertions")
