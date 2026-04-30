"""
Milestone R, Plan A — verify the synthesizer speaks the popular-education
organizing tradition (re:power, Wellstone, Ruckus) instead of generic
political-marketing voice.

Covers:
  Section 1 — Power type inference (_infer_power_type)
              Through / Over / With keyword scoring, tiebreaker, agent-list signal.
  Section 2 — Constants (POWER_TYPES, ORGANIZING_GLOSSARY, GENERIC_TO_ORGANIZER, SYSTEM_PROMPT)
              Shape and presence of canonical vocabulary; Theory of Change directive
              in the system prompt; no marketing-language directive.
  Section 3 — _build_prompt output
              Power-type block, glossary block, "What This Won't Do" instruction
              are all present in both the plan and non-plan branches.
  Section 4 — export_node end-to-end (LLM call mocked)
              The node stamps a power_type entry into structured_data and the
              prompt sent to the LLM contains the organizer-voice scaffolding.
"""

import os, sys, types
from pathlib import Path
from unittest.mock import patch

PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "powerbuilder_app.settings")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-validation-only")
os.environ["DEBUG"] = "True"
os.environ.setdefault("DEMO_PASSWORD", "fieldwork-mobilize-78")
os.environ["ALLOWED_HOSTS"] = "testserver,localhost,127.0.0.1"

import django; django.setup()

from chat.agents import export as export_mod
from chat.agents.export import (
    _infer_power_type,
    _build_prompt,
    POWER_TYPES,
    ORGANIZING_GLOSSARY,
    GENERIC_TO_ORGANIZER,
    SYSTEM_PROMPT,
    export_node,
)

assertions = 0


def check(condition, message):
    global assertions
    assertions += 1
    if not condition:
        raise AssertionError(message)


# -----------------------------------------------------------------------------
# Section 1 — Power type inference
# -----------------------------------------------------------------------------

# 1a. Electoral / partisan queries → Power Through
check(
    _infer_power_type("Help me run a campaign for state senate in district 14") == "through",
    "electoral query should infer Power Through",
)
check(
    _infer_power_type("Plan voter turnout in Gwinnett County precincts") == "through",
    "voter/precinct query should infer Power Through",
)
check(
    _infer_power_type("What's our win number for the primary?") == "through",
    "win number / primary should infer Power Through",
)

# 1b. Pressure / decision-maker queries → Power Over
check(
    _infer_power_type(
        "Build escalation plan to pressure the city council to pass tenant protections"
    ) == "over",
    "pressure + city council + escalation should infer Power Over",
)
check(
    _infer_power_type("Plan a march to demand corporate accountability from Acme") == "over",
    "march + demand + corporate should infer Power Over",
)

# 1c. Alternative-structure / mutual-aid queries → Power With
check(
    _infer_power_type(
        "Help us start a mutual aid network and run know your rights trainings"
    ) == "with",
    "mutual aid + know your rights should infer Power With",
)
check(
    _infer_power_type(
        "We're doing base building and leader development for a tenant union"
    ) == "with",
    "base building + leader development should infer Power With",
)

# 1d. Empty / unknown query → fallback Through
check(
    _infer_power_type("") == "through",
    "empty query should fall back to Power Through",
)
check(
    _infer_power_type("how is the weather") == "through",
    "irrelevant query should fall back to Power Through",
)

# 1e. Agent-list signal (electoral agents add a Through point on tiebreak)
check(
    _infer_power_type("plan", active_agents=["win_number", "precincts"]) == "through",
    "electoral agent list alone should infer Power Through",
)

# 1f. Strong "over" keywords still beat one electoral agent point
check(
    _infer_power_type(
        "march escalation pressure decision-maker boycott protest disrupt",
        active_agents=["election_results"],
    ) == "over",
    "many over-keywords should outscore one electoral agent point",
)

print(f"PASS — Section 1 (power type inference): 11 assertions")


# -----------------------------------------------------------------------------
# Section 2 — Constants
# -----------------------------------------------------------------------------

check(set(POWER_TYPES.keys()) == {"through", "over", "with"}, "POWER_TYPES has the three keys")
for key, meta in POWER_TYPES.items():
    check("label" in meta and meta["label"].startswith("Power "), f"POWER_TYPES[{key}] has label")
    check("definition" in meta and len(meta["definition"]) > 20, f"POWER_TYPES[{key}] has definition")

# Glossary anchors — top concepts from the corpus must be named.
for term in [
    "base", "persuadable", "target", "ladder of engagement", "rung",
    "spectrum of allies", "escalation", "PSAA", "theory of change",
    "mobilize vs. organize", "declare victory and run",
]:
    check(term in ORGANIZING_GLOSSARY, f"ORGANIZING_GLOSSARY contains '{term}'")

# Generic-to-organizer anti-marketing block.
for forbidden_target in ["followers", "audience", "engagement funnel", "call to action"]:
    check(
        forbidden_target in GENERIC_TO_ORGANIZER,
        f"GENERIC_TO_ORGANIZER instructs replacement of '{forbidden_target}'",
    )

# System prompt enforces the three core organizer-voice rules.
check("Theory of Change" in SYSTEM_PROMPT, "SYSTEM_PROMPT names Theory of Change")
check("If we do X, then Y will happen" in SYSTEM_PROMPT, "SYSTEM_PROMPT supplies the ToC sentence frame")
check("popular-education" in SYSTEM_PROMPT.lower() or "popular education" in SYSTEM_PROMPT.lower(),
      "SYSTEM_PROMPT names the popular-education tradition")
check("re:power" in SYSTEM_PROMPT, "SYSTEM_PROMPT names re:power lineage")
check("ladder" in SYSTEM_PROMPT.lower(), "SYSTEM_PROMPT names the ladder of engagement")
check("marketing" in SYSTEM_PROMPT.lower(), "SYSTEM_PROMPT calls out generic marketing language to avoid")

print(f"PASS — Section 2 (constants): 25 assertions")


# -----------------------------------------------------------------------------
# Section 3 — _build_prompt output
# -----------------------------------------------------------------------------

# Plan-mode prompt
plan_prompt = _build_prompt(
    query="Plan a state senate run",
    research_context="District is suburban; 2024 turnout was 62%.",
    structured_context="[{'agent':'win_number','target_votes':24500}]",
    active_agents=["researcher", "win_number", "precincts", "messaging", "cost_calculator", "election_results"],
    errors=[],
    is_plan=True,
    district_label="State Senate District 14",
    power_type="through",
)
check("INFERRED POWER TYPE: Power Through" in plan_prompt, "plan prompt names inferred Power Through")
check("CANONICAL ORGANIZING VOCABULARY" in plan_prompt, "plan prompt includes glossary header")
check("ladder of engagement" in plan_prompt, "plan prompt includes ladder term from glossary")
check("What This Won\u2019t Do" in plan_prompt, "plan prompt instructs the won't-do footer (curly apostrophe)")
check("rung on the ladder of engagement" in plan_prompt,
      "plan prompt asks recommendations to be tagged as rungs")
check("Theory of Change" in plan_prompt or "theory of change" in plan_prompt,
      "plan prompt names Theory of Change in some form")
check("USER REQUEST: Plan a state senate run" in plan_prompt, "plan prompt echoes the user request")

# Non-plan prompt
brief_prompt = _build_prompt(
    query="Help me write a tenant pressure post",
    research_context="No research available.",
    structured_context="No structured data.",
    active_agents=["messaging"],
    errors=[],
    is_plan=False,
    district_label="—",
    power_type="over",
)
check("INFERRED POWER TYPE: Power Over" in brief_prompt, "non-plan prompt names inferred Power Over")
check("If we do X, then Y will happen" in brief_prompt,
      "non-plan prompt requires explicit Theory of Change sentence frame")
check("What This Won\u2019t Do" in brief_prompt, "non-plan prompt instructs the won't-do footer")
check("CANONICAL ORGANIZING VOCABULARY" in brief_prompt, "non-plan prompt includes glossary header")

# Errors block still works.
err_prompt = _build_prompt(
    query="x", research_context="r", structured_context="s",
    active_agents=[], errors=["finance: timeout"],
    is_plan=False, district_label="—", power_type="with",
)
check("finance: timeout" in err_prompt, "errors are surfaced into the prompt")
check("INFERRED POWER TYPE: Power With" in err_prompt, "Power With label is rendered when chosen")

print(f"PASS — Section 3 (build_prompt): 13 assertions")


# -----------------------------------------------------------------------------
# Section 4 — export_node end-to-end (LLM mocked)
# -----------------------------------------------------------------------------

class _FakeMsg:
    def __init__(self, text): self.content = text


class _FakeLLM:
    def __init__(self):
        self.last_messages = None
    def invoke(self, messages):
        self.last_messages = messages
        return _FakeMsg("# Briefing\n\nTheory of Change: If we do X, then Y.\n")


fake_llm = _FakeLLM()


def _fake_get_completion_client(temperature=0.3):
    return fake_llm


with patch.object(export_mod, "get_completion_client", _fake_get_completion_client):
    state = {
        "query": "Plan voter turnout for the primary in district 14",
        "research_results": ["Suburban district, 62% 2024 turnout"],
        "structured_data": [{"agent": "win_number", "target_votes": 24500}],
        "active_agents": ["researcher", "win_number"],
        "errors": [],
        "output_format": "text",
    }
    out = export_node(state)

# Power type stamped into result.structured_data (LangGraph appends via operator.add).
sd = out.get("structured_data", [])
check(isinstance(sd, list) and len(sd) == 1, "export_node returns exactly one structured_data row")
power_row = sd[0]
check(power_row.get("agent") == "power_type", "the row is the power_type entry")
check(power_row.get("power_type") == "through", "voter/primary/district query → Power Through")
check(power_row.get("label") == "Power Through", "label is rendered for the UI chip")

# The actual prompt sent to the LLM carries the organizer-voice scaffolding.
sent = fake_llm.last_messages
check(sent is not None and len(sent) == 2, "LLM was called with system + user messages")
check(sent[0]["role"] == "system" and "Theory of Change" in sent[0]["content"],
      "system message carries the Theory of Change directive")
check("INFERRED POWER TYPE: Power Through" in sent[1]["content"],
      "user prompt carries the inferred Power Through label")
check("CANONICAL ORGANIZING VOCABULARY" in sent[1]["content"],
      "user prompt carries the glossary block")
check("What This Won\u2019t Do" in sent[1]["content"],
      "user prompt carries the won't-do instruction")

# final_answer is set even though the LLM was mocked.
check("final_answer" in out and out["final_answer"], "export_node sets final_answer")

print(f"PASS — Section 4 (export_node end-to-end): 10 assertions")

print(f"\nALL PASS — {assertions} assertions")
