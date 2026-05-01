"""
chat/utils/provider_choice.py

Milestone R: parse + validate the user's per-request LLM provider override
and persist their choice to a JSONL log so we can analyze model preferences
without standing up a database table.

The picker UI lives in templates/chat.html as a hidden input
(name="llm_provider"), driven by a <select> in the input bar. Both the
HTMX /send/ POST path and the SSE /stream/ GET path call parse_provider()
with the raw request value to get a clean provider string (or None to fall
back to the default) before handing it to manager.run_query().

This module is deliberately tiny and side-effect-light: parsing returns
None for empty / unknown values, and logging swallows its own errors so a
disk hiccup never blocks an answer from rendering.
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Optional

from .llm_config import (
    LLM_PROVIDER,
    SUPPORTED_PROVIDERS,
    _DEFAULT_MODELS,
)

logger = logging.getLogger(__name__)

# Friendly display names for each provider, used in the "Powered by" chip
# and the picker dropdown. Kept in this file (not llm_config) because it's
# a UX concern, not a registry concern. New providers added to
# SUPPORTED_PROVIDERS will fall back to a Title-cased version of the key
# until they're added here.
PROVIDER_DISPLAY_NAMES: dict[str, str] = {
    "openai":    "OpenAI",
    "anthropic": "Anthropic",
    "gemini":    "Gemini",
    "llama":     "Llama",
    "mistral":   "Mistral",
    "cohere":    "Cohere",
    "groq":      "Groq",
}


def provider_label(provider: Optional[str]) -> str:
    """
    Return a "Provider · model" string for the resolved provider, e.g.
    "Anthropic · claude-sonnet-4-5". Used by the "Powered by" chip on the
    response bubble. Falls back to the env-default LLM_PROVIDER when the
    caller passed None (which happens when the picker was left untouched).
    """
    active = (provider or LLM_PROVIDER or "openai").lower().strip()
    name = PROVIDER_DISPLAY_NAMES.get(active, active.title())
    model = _DEFAULT_MODELS.get(active, "")
    return f"{name} · {model}" if model else name

# Where to append per-request provider choices. Mirrors EXPORTS_DIR in
# test_llm_comparison.py so reports + raw votes live next to each other.
EXPORTS_DIR = os.getenv(
    "EXPORTS_DIR",
    os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "exports")
    ),
)
CHOICES_LOG_PATH = os.path.join(EXPORTS_DIR, "model_choices.jsonl")


def parse_provider(raw: Optional[str]) -> Optional[str]:
    """
    Normalize a raw provider string from a POST/GET parameter.

    Returns:
        - The lowercase provider name if it's in SUPPORTED_PROVIDERS.
        - None if raw is empty, missing, or unknown (caller falls back
          to the env-default LLM_PROVIDER, which today is "openai").

    We never raise: an unknown picker value should silently fall back to
    the default rather than 500-ing on the user. Misconfigured pickers
    are a UX bug, not a request failure.
    """
    if not raw:
        return None
    cleaned = raw.strip().lower()
    if not cleaned:
        return None
    if cleaned not in SUPPORTED_PROVIDERS:
        logger.info("Ignoring unsupported llm_provider value: %r", cleaned)
        return None
    return cleaned


def log_choice(
    *,
    provider: Optional[str],
    query: str,
    org_namespace: str,
    path: str,
) -> None:
    """
    Append one JSON line to exports/model_choices.jsonl recording which
    provider answered which query. Quietly no-ops on filesystem errors so
    logging never blocks the user-facing response.

    Each line:
        {
          "ts": 1714521234.5,
          "provider": "anthropic" | None,
          "query": "...",         # truncated to 500 chars
          "org_namespace": "...",
          "path": "post" | "stream",
        }
    """
    try:
        os.makedirs(EXPORTS_DIR, exist_ok=True)
        record = {
            "ts": round(time.time(), 1),
            "provider": provider,
            "query": (query or "")[:500],
            "org_namespace": org_namespace or "",
            "path": path,
        }
        with open(CHOICES_LOG_PATH, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError as exc:
        logger.warning("model_choices.jsonl append failed: %s", exc)
