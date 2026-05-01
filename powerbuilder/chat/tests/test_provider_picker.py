# powerbuilder/chat/tests/test_provider_picker.py
"""
Milestone R: unit tests for the LLM provider picker.

Covers the three pieces that make the picker work end-to-end:
  1. parse_provider() — defensive normalization of the raw POST/GET value
  2. log_choice()    — JSONL append to exports/model_choices.jsonl
  3. provider_label() — "Provider · model" string for the response chip
  4. provider_override() / get_active_provider() — contextvar plumbing in
     llm_config that lets a request pin a provider for downstream
     get_completion_client() calls without threading it through every
     agent signature.

These are pure-Python unit tests (no Django, no network, no LLM calls),
runnable with:
    cd powerbuilder
    python -m pytest chat/tests/test_provider_picker.py -v
"""

from __future__ import annotations

import json
import os
import sys
from unittest.mock import patch

import pytest

# Path setup so the tests can be run from the repo root or directly.
sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
)

from chat.utils import provider_choice
from chat.utils.provider_choice import (
    PROVIDER_DISPLAY_NAMES,
    log_choice,
    parse_provider,
    provider_label,
)
from chat.utils.llm_config import (
    LLM_PROVIDER,
    SUPPORTED_PROVIDERS,
    get_active_provider,
    provider_override,
)


# ── parse_provider ────────────────────────────────────────────────────────────


@pytest.mark.parametrize("provider", SUPPORTED_PROVIDERS)
def test_parse_provider_valid(provider):
    """Every provider in the registry round-trips through parse_provider."""
    assert parse_provider(provider) == provider


@pytest.mark.parametrize("raw", [None, "", "   ", "\t\n"])
def test_parse_provider_empty(raw):
    """Blank / whitespace / None all fall back to default (None)."""
    assert parse_provider(raw) is None


@pytest.mark.parametrize("raw", ["fakeprovider", "GPT4", "claude", "azureml"])
def test_parse_provider_unknown(raw):
    """Unknown provider names return None silently, never raise."""
    assert parse_provider(raw) is None


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("OPENAI", "openai"),
        ("OpenAI", "openai"),
        ("  Anthropic  ", "anthropic"),
        ("GEMINI", "gemini"),
    ],
)
def test_parse_provider_case_insensitive(raw, expected):
    """Whitespace and case are normalized before SUPPORTED_PROVIDERS lookup."""
    assert parse_provider(raw) == expected


# ── log_choice ────────────────────────────────────────────────────────────────


def test_log_choice_appends_jsonl(tmp_path, monkeypatch):
    """One call appends one valid JSON line with the expected fields."""
    monkeypatch.setattr(provider_choice, "EXPORTS_DIR", str(tmp_path))
    monkeypatch.setattr(
        provider_choice, "CHOICES_LOG_PATH", str(tmp_path / "model_choices.jsonl")
    )

    log_choice(
        provider="anthropic",
        query="Where do I knock in HD-22?",
        org_namespace="testorg",
        path="post",
    )

    log_path = tmp_path / "model_choices.jsonl"
    assert log_path.exists(), "log file should be created on first append"

    lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])

    assert record["provider"] == "anthropic"
    assert record["query"] == "Where do I knock in HD-22?"
    assert record["org_namespace"] == "testorg"
    assert record["path"] == "post"
    assert isinstance(record["ts"], (int, float))


def test_log_choice_multiple_appends(tmp_path, monkeypatch):
    """Repeated calls append (don't overwrite) and preserve order."""
    monkeypatch.setattr(provider_choice, "EXPORTS_DIR", str(tmp_path))
    monkeypatch.setattr(
        provider_choice, "CHOICES_LOG_PATH", str(tmp_path / "model_choices.jsonl")
    )

    for i, prov in enumerate(["openai", "gemini", None]):
        log_choice(
            provider=prov,
            query=f"q{i}",
            org_namespace="testorg",
            path="stream",
        )

    lines = (tmp_path / "model_choices.jsonl").read_text().strip().splitlines()
    assert len(lines) == 3
    assert [json.loads(line)["provider"] for line in lines] == [
        "openai",
        "gemini",
        None,
    ]


def test_log_choice_truncates_long_query(tmp_path, monkeypatch):
    """Queries over 500 chars are truncated to keep the log readable."""
    monkeypatch.setattr(provider_choice, "EXPORTS_DIR", str(tmp_path))
    monkeypatch.setattr(
        provider_choice, "CHOICES_LOG_PATH", str(tmp_path / "model_choices.jsonl")
    )

    log_choice(
        provider="openai",
        query="x" * 5000,
        org_namespace="testorg",
        path="post",
    )

    record = json.loads((tmp_path / "model_choices.jsonl").read_text().strip())
    assert len(record["query"]) == 500


def test_log_choice_swallows_oserror(tmp_path, monkeypatch):
    """A disk failure must never bubble up and break the response."""
    monkeypatch.setattr(provider_choice, "EXPORTS_DIR", str(tmp_path))
    monkeypatch.setattr(
        provider_choice, "CHOICES_LOG_PATH", str(tmp_path / "model_choices.jsonl")
    )

    with patch(
        "chat.utils.provider_choice.open",
        side_effect=OSError("disk full"),
        create=True,
    ):
        # No exception should escape — that's the entire contract.
        log_choice(
            provider="openai",
            query="hello",
            org_namespace="testorg",
            path="post",
        )


# ── provider_label ────────────────────────────────────────────────────────────


def test_provider_label_known():
    """Known providers render as 'Display Name · model'."""
    label = provider_label("anthropic")
    assert label.startswith("Anthropic")
    assert "·" in label
    # Model string is non-empty for the canonical providers.
    assert label.split("·")[1].strip()


def test_provider_label_fallback():
    """None falls back to the env-default LLM_PROVIDER."""
    label = provider_label(None)
    expected_display = PROVIDER_DISPLAY_NAMES.get(
        LLM_PROVIDER.lower(), LLM_PROVIDER.title()
    )
    assert label.startswith(expected_display)


def test_provider_label_handles_case_and_whitespace():
    """Casing/whitespace shouldn't break the lookup."""
    assert provider_label("  ANTHROPIC  ").startswith("Anthropic")


def test_provider_label_unknown_provider():
    """Unknown names still produce a usable label (Title-cased fallback)."""
    label = provider_label("acmecorp")
    # Should at least Title-case the unknown key without crashing.
    assert label.lower().startswith("acmecorp")


# ── provider_override / get_active_provider ──────────────────────────────────


def test_provider_override_sets_and_resets():
    """The contextvar is visible inside the block and reverts on exit."""
    before = get_active_provider()

    with provider_override("gemini"):
        assert get_active_provider() == "gemini"

    # After exit we're back to whatever was active before.
    assert get_active_provider() == before


def test_provider_override_noop_on_none():
    """provider_override(None) must not change the active provider."""
    before = get_active_provider()

    with provider_override(None):
        assert get_active_provider() == before

    assert get_active_provider() == before


def test_provider_override_noop_on_blank():
    """Empty string is treated like None — fall back to default."""
    before = get_active_provider()

    with provider_override(""):
        # Either keeps `before` or coerces to default; both are valid.
        assert get_active_provider() == before

    assert get_active_provider() == before


def test_provider_override_normalizes_case():
    """Override input is case/whitespace-insensitive."""
    with provider_override("  ANTHROPIC  "):
        assert get_active_provider() == "anthropic"


def test_provider_override_nested():
    """Nested overrides restore the outer value on inner exit."""
    with provider_override("gemini"):
        assert get_active_provider() == "gemini"
        with provider_override("anthropic"):
            assert get_active_provider() == "anthropic"
        # Inner block exited — outer override is back in effect.
        assert get_active_provider() == "gemini"


# ── manager.run_query plumbing (smoke test, no LLM call) ──────────────────────

# These two tests import chat.agents.manager which transitively imports
# langgraph. Skip cleanly if it's not installed (e.g. minimal CI image)
# rather than fail with ModuleNotFoundError.


def test_run_query_passes_llm_provider_to_override(monkeypatch):
    """
    Regression guard: run_query() must wrap manager_app.invoke() in
    provider_override(llm_provider) so downstream get_completion_client()
    calls see the picked provider.
    """
    pytest.importorskip("langgraph", reason="langgraph not installed")
    from chat.agents import manager as manager_module

    captured: dict = {}

    def fake_invoke(initial_state, config=None):
        # While invoke is running, the contextvar should reflect the picked
        # provider — that's the entire point of the override.
        captured["active_during_invoke"] = get_active_provider()
        captured["initial_state"] = initial_state
        return {"final_answer": "ok", "active_agents": [], "errors": []}

    monkeypatch.setattr(manager_module.manager_app, "invoke", fake_invoke)

    result = manager_module.run_query(
        query="hello",
        org_namespace="testorg",
        llm_provider="anthropic",
    )

    assert captured["active_during_invoke"] == "anthropic"
    # And the override is released once run_query returns.
    assert get_active_provider() != "anthropic" or LLM_PROVIDER.lower() == "anthropic"
    # The chosen provider is echoed back for the view to render the chip.
    assert result["llm_provider"] == "anthropic"
    assert result["org_namespace"] == "testorg"


def test_run_query_default_when_no_provider(monkeypatch):
    """When llm_provider is None, the override is a no-op."""
    pytest.importorskip("langgraph", reason="langgraph not installed")
    from chat.agents import manager as manager_module

    captured: dict = {}
    default_active = get_active_provider()

    def fake_invoke(initial_state, config=None):
        captured["active_during_invoke"] = get_active_provider()
        return {"final_answer": "ok", "active_agents": [], "errors": []}

    monkeypatch.setattr(manager_module.manager_app, "invoke", fake_invoke)

    result = manager_module.run_query(
        query="hello",
        org_namespace="testorg",
        llm_provider=None,
    )

    # No override picked → active provider equals the env default.
    assert captured["active_during_invoke"] == default_active
    assert result["llm_provider"] is None


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
