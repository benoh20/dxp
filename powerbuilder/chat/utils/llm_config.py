"""
chat/utils/llm_config.py

Central LLM configuration for Powerbuilder.

Usage:
    from chat.utils.llm_config import get_completion_client, get_embedding_client

Normal mode (COMPARISON_MODE=False, default)
--------------------------------------------
  Completion: controlled by LLM_PROVIDER env var (default "openai").
  Embeddings: always OpenAI text-embedding-3-small → OPENAI_PINECONE_INDEX_NAME.
  This keeps Pinecone retrieval stable regardless of which LLM is active.

Comparison mode (COMPARISON_MODE=True)
---------------------------------------
  Both completion AND embedding route to the same provider.
  Each provider uses its own Pinecone index so retrieval results are
  directly comparable across models:

    powerbuilder-openai    OpenAI text-embedding-3-small   1536 dims
    powerbuilder-google    Google text-embedding-004        768 dims
    powerbuilder-mistral   Mistral mistral-embed           1024 dims
    powerbuilder-cohere    Cohere embed-english-v3.0       1024 dims
    powerbuilder-llama     BAAI/bge-base-en-v1.5 (Together) 768 dims
    powerbuilder-openai    anthropic fallback (no native)  1536 dims
    powerbuilder-openai    groq fallback (no native)       1536 dims

Supported providers
-------------------
  openai      gpt-4o                        OPENAI_API_KEY
  anthropic   claude-sonnet-4-5             ANTHROPIC_API_KEY
  gemini      gemini-1.5-pro                GOOGLE_API_KEY
  llama       llama-3.1-70b-versatile       GROQ_API_KEY (preferred) or LLAMA_API_KEY
  mistral     mistral-large-latest          MISTRAL_API_KEY
  cohere      command-r-plus                COHERE_API_KEY
  groq        llama-3.1-70b-versatile       GROQ_API_KEY

Custom providers can be registered at runtime via register_custom_provider().
ChangeAgent will use this hook without modifying this file.
"""

import os
from typing import Any, Callable, NamedTuple

from dotenv import load_dotenv
load_dotenv()

# ---------------------------------------------------------------------------
# Provider registry
# ---------------------------------------------------------------------------

SUPPORTED_PROVIDERS = [
    "openai",
    "anthropic",
    "gemini",
    "llama",
    "mistral",
    "cohere",
    "groq",
]

# Default completion model for each provider
_DEFAULT_MODELS: dict[str, str] = {
    "openai":    "gpt-4o",
    "anthropic": "claude-sonnet-4-5",
    "gemini":    "gemini-1.5-pro",
    "llama":     "llama-3.1-70b-versatile",
    "mistral":   "mistral-large-latest",
    "cohere":    "command-r-plus",
    "groq":      "llama-3.1-70b-versatile",
}

# Default native embedding model per provider.
# None means the provider has no embedding API; falls back to OpenAI.
_DEFAULT_EMBEDDING_MODELS: dict[str, str | None] = {
    "openai":    "text-embedding-3-small",
    "anthropic": None,                          # no native embedding API
    "gemini":    "models/text-embedding-004",
    "llama":     "BAAI/bge-base-en-v1.5",       # via Together.ai
    "mistral":   "mistral-embed",
    "cohere":    "embed-english-v3.0",
    "groq":      None,                          # inference-only, no embeddings
}

# Pinecone index name for each provider's native embedding space.
# Providers without native embeddings map to the OpenAI index so they
# can still do retrieval using the shared OpenAI embedding space.
PINECONE_INDEX_NAMES: dict[str, str] = {
    "openai":    "powerbuilder-openai",
    "anthropic": "powerbuilder-openai",   # fallback — no native embeddings
    "gemini":    "powerbuilder-google",
    "llama":     "powerbuilder-llama",
    "mistral":   "powerbuilder-mistral",
    "cohere":    "powerbuilder-cohere",
    "groq":      "powerbuilder-openai",   # fallback — no native embeddings
}

# Output dimensions for each provider's embedding model.
# Providers without native embeddings inherit OpenAI's 1536-dim space.
EMBEDDING_DIMENSIONS: dict[str, int] = {
    "openai":    1536,
    "anthropic": 1536,   # uses openai embeddings
    "gemini":    768,
    "llama":     768,
    "mistral":   1024,
    "cohere":    1024,
    "groq":      1536,   # uses openai embeddings
}

# Registry for custom providers added via register_custom_provider().
_custom_registry: dict[str, Callable] = {}

# ---------------------------------------------------------------------------
# Mode flags — read once at import time
# ---------------------------------------------------------------------------

LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "openai").lower().strip()

# When True: both embedding and completion route to the same provider and its
# dedicated Pinecone index.  Used by comparison_ingestor and test_llm_comparison.
COMPARISON_MODE: bool = os.getenv("COMPARISON_MODE", "false").lower() in ("1", "true", "yes")


# ---------------------------------------------------------------------------
# Embedding return type
# ---------------------------------------------------------------------------

class EmbeddingConfig(NamedTuple):
    """
    Everything a caller needs to do a Pinecone search with a specific provider.

    Attributes:
        client:     LangChain embedding object (implements embed_query / embed_documents).
        index_name: Name of the Pinecone index that holds vectors for this embedding space.
        dimensions: Vector output size — used when creating a new index.
        provider:   Which provider produced this config (for logging).
        model:      Embedding model name (for logging).
    """
    client:     Any
    index_name: str
    dimensions: int
    provider:   str
    model:      str


# ---------------------------------------------------------------------------
# Custom provider registration
# ---------------------------------------------------------------------------

def register_custom_provider(name: str, client_factory: Callable) -> None:
    """
    Register a custom LLM provider without modifying llm_config.py.

    Args:
        name:           Unique provider name (e.g. "change_agent").
        client_factory: Zero-argument callable that returns an initialised
                        LangChain chat model (anything with a .invoke() method).

    ChangeAgent will call this once at startup to slot in its own client
    without touching the core llm_config logic.
    """
    _custom_registry[name.lower().strip()] = client_factory


# ---------------------------------------------------------------------------
# Completion client factory
# ---------------------------------------------------------------------------

def get_completion_client(
    temperature: float = 0.3,
    provider: str | None = None,
):
    """
    Return an initialised LangChain chat model for the active (or specified) provider.

    Args:
        temperature: Sampling temperature.
        provider:    Override LLM_PROVIDER for this call.

    Raises:
        ValueError:   Unknown provider name.
        RuntimeError: Required API key missing.
    """
    active = (provider or LLM_PROVIDER).lower().strip()

    if active in _custom_registry:
        return _custom_registry[active]()

    if active == "openai":
        from langchain_openai import ChatOpenAI
        key = os.getenv("OPENAI_API_KEY")
        if not key:
            raise RuntimeError("LLM_PROVIDER=openai but OPENAI_API_KEY is not set.")
        return ChatOpenAI(model=_DEFAULT_MODELS["openai"], temperature=temperature, openai_api_key=key)

    if active == "anthropic":
        from langchain_anthropic import ChatAnthropic
        key = os.getenv("ANTHROPIC_API_KEY")
        if not key:
            raise RuntimeError("LLM_PROVIDER=anthropic but ANTHROPIC_API_KEY is not set.")
        return ChatAnthropic(model=_DEFAULT_MODELS["anthropic"], temperature=temperature, anthropic_api_key=key)

    if active == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI
        key = os.getenv("GOOGLE_API_KEY")
        if not key:
            raise RuntimeError("LLM_PROVIDER=gemini but GOOGLE_API_KEY is not set.")
        return ChatGoogleGenerativeAI(model=_DEFAULT_MODELS["gemini"], temperature=temperature, google_api_key=key)

    if active == "llama":
        groq_key  = os.getenv("GROQ_API_KEY")
        llama_key = os.getenv("LLAMA_API_KEY")
        if groq_key:
            from langchain_groq import ChatGroq
            return ChatGroq(model=_DEFAULT_MODELS["llama"], temperature=temperature, groq_api_key=groq_key)
        if llama_key:
            from langchain_openai import ChatOpenAI
            return ChatOpenAI(
                model=_DEFAULT_MODELS["llama"], temperature=temperature,
                openai_api_key=llama_key, openai_api_base="https://api.together.xyz/v1",
            )
        raise RuntimeError("LLM_PROVIDER=llama but neither GROQ_API_KEY nor LLAMA_API_KEY is set.")

    if active == "mistral":
        from langchain_mistralai import ChatMistralAI
        key = os.getenv("MISTRAL_API_KEY")
        if not key:
            raise RuntimeError("LLM_PROVIDER=mistral but MISTRAL_API_KEY is not set.")
        return ChatMistralAI(model=_DEFAULT_MODELS["mistral"], temperature=temperature, mistral_api_key=key)

    if active == "cohere":
        from langchain_cohere import ChatCohere
        key = os.getenv("COHERE_API_KEY")
        if not key:
            raise RuntimeError("LLM_PROVIDER=cohere but COHERE_API_KEY is not set.")
        return ChatCohere(model=_DEFAULT_MODELS["cohere"], temperature=temperature, cohere_api_key=key)

    if active == "groq":
        from langchain_groq import ChatGroq
        key = os.getenv("GROQ_API_KEY")
        if not key:
            raise RuntimeError("LLM_PROVIDER=groq but GROQ_API_KEY is not set.")
        return ChatGroq(model=_DEFAULT_MODELS["groq"], temperature=temperature, groq_api_key=key)

    raise ValueError(
        f"Unknown LLM provider: '{active}'. "
        f"Supported: {SUPPORTED_PROVIDERS}. "
        "Use register_custom_provider() to add a new one."
    )


# ---------------------------------------------------------------------------
# Embedding client factory
# ---------------------------------------------------------------------------

def get_embedding_client(provider: str | None = None) -> EmbeddingConfig:
    """
    Return an EmbeddingConfig for the requested provider.

    Normal mode (COMPARISON_MODE=False, provider=None):
        Always returns OpenAI text-embedding-3-small pointing at
        OPENAI_PINECONE_INDEX_NAME.  This is the stable production path.

    Comparison mode (COMPARISON_MODE=True) or explicit provider:
        Returns the provider's native embedding model and its dedicated
        Pinecone index.  Providers without native embeddings (anthropic,
        groq) transparently fall back to OpenAI so retrieval still works.

    Args:
        provider: Force a specific provider.  Defaults to LLM_PROVIDER when
                  COMPARISON_MODE=True, or "openai" in normal mode.

    Returns:
        EmbeddingConfig(client, index_name, dimensions, provider, model)
    """
    if provider is None:
        active = LLM_PROVIDER if COMPARISON_MODE else "openai"
    else:
        active = provider.lower().strip()

    emb_model = _DEFAULT_EMBEDDING_MODELS.get(active)
    has_native = emb_model is not None

    # Providers without native embeddings fall back to OpenAI
    if not has_native:
        active_for_embed = "openai"
        emb_model = _DEFAULT_EMBEDDING_MODELS["openai"]
    else:
        active_for_embed = active

    # Index name: provider-specific when in comparison mode or provider requested;
    # otherwise use the env-configured production index
    if provider is not None or COMPARISON_MODE:
        index_name = PINECONE_INDEX_NAMES.get(active, PINECONE_INDEX_NAMES["openai"])
    else:
        index_name = os.getenv("OPENAI_PINECONE_INDEX_NAME", PINECONE_INDEX_NAMES["openai"])

    dimensions = EMBEDDING_DIMENSIONS.get(active, 1536)
    client     = _build_embedding_client(active_for_embed, emb_model)

    return EmbeddingConfig(
        client=client,
        index_name=index_name,
        dimensions=dimensions,
        provider=active_for_embed,
        model=emb_model,
    )


def _build_embedding_client(provider: str, model: str):
    """Construct the LangChain embedding object for the given provider + model."""

    if provider == "openai":
        from langchain_openai import OpenAIEmbeddings
        key = os.getenv("OPENAI_API_KEY")
        if not key:
            raise RuntimeError("OPENAI_API_KEY is required for OpenAI embeddings.")
        return OpenAIEmbeddings(model=model, openai_api_key=key)

    if provider == "gemini":
        from langchain_google_genai import GoogleGenerativeAIEmbeddings
        key = os.getenv("GOOGLE_API_KEY")
        if not key:
            raise RuntimeError("GOOGLE_API_KEY is required for Google embeddings.")
        return GoogleGenerativeAIEmbeddings(model=model, google_api_key=key)

    if provider == "mistral":
        from langchain_mistralai import MistralAIEmbeddings
        key = os.getenv("MISTRAL_API_KEY")
        if not key:
            raise RuntimeError("MISTRAL_API_KEY is required for Mistral embeddings.")
        return MistralAIEmbeddings(model=model, mistral_api_key=key)

    if provider == "cohere":
        from langchain_cohere import CohereEmbeddings
        key = os.getenv("COHERE_API_KEY")
        if not key:
            raise RuntimeError("COHERE_API_KEY is required for Cohere embeddings.")
        return CohereEmbeddings(model=model, cohere_api_key=key)

    if provider == "llama":
        # Together.ai hosts open embedding models via OpenAI-compatible API
        key = os.getenv("LLAMA_API_KEY")
        if not key:
            raise RuntimeError("LLAMA_API_KEY is required for Llama embeddings via Together.ai.")
        from langchain_openai import OpenAIEmbeddings
        return OpenAIEmbeddings(
            model=model,
            openai_api_key=key,
            openai_api_base="https://api.together.xyz/v1",
        )

    raise ValueError(f"No embedding client available for provider '{provider}'.")


# ---------------------------------------------------------------------------
# Introspection helpers
# ---------------------------------------------------------------------------

def get_provider_info(provider: str | None = None) -> dict:
    """
    Return the active provider name, completion model, and embedding model.

    Returns:
        {
          "provider":        str,
          "model":           str,   # completion model
          "embedding_model": str,   # native embedding model (or None)
          "index_name":      str,   # target Pinecone index
          "comparison_mode": bool,
        }
    """
    active = (provider or LLM_PROVIDER).lower().strip()
    return {
        "provider":        active,
        "model":           _DEFAULT_MODELS.get(active, "custom"),
        "embedding_model": _DEFAULT_EMBEDDING_MODELS.get(active),
        "index_name":      PINECONE_INDEX_NAMES.get(active, PINECONE_INDEX_NAMES["openai"]),
        "comparison_mode": COMPARISON_MODE,
    }


def get_configured_providers() -> list[dict]:
    """
    Return info for every provider whose API key(s) are currently configured.
    Used by comparison_ingestor and test_llm_comparison to skip unconfigured providers.

    Returns:
        List of dicts, each like get_provider_info() plus "embedding_available".
    """
    key_map = {
        "openai":    ["OPENAI_API_KEY"],
        "anthropic": ["ANTHROPIC_API_KEY"],
        "gemini":    ["GOOGLE_API_KEY"],
        "llama":     ["GROQ_API_KEY", "LLAMA_API_KEY"],   # either key works
        "mistral":   ["MISTRAL_API_KEY"],
        "cohere":    ["COHERE_API_KEY"],
        "groq":      ["GROQ_API_KEY"],
    }
    # Which providers can produce native embeddings (have both key AND native model)
    embed_key_map = {
        "openai":  ["OPENAI_API_KEY"],
        "gemini":  ["GOOGLE_API_KEY"],
        "mistral": ["MISTRAL_API_KEY"],
        "cohere":  ["COHERE_API_KEY"],
        "llama":   ["LLAMA_API_KEY"],   # Together.ai only — GROQ_API_KEY not usable for embeddings
    }

    results = []
    for p in SUPPORTED_PROVIDERS:
        keys_needed = key_map.get(p, [])
        completion_ok = any(os.getenv(k) for k in keys_needed)
        if not completion_ok:
            continue
        embed_keys = embed_key_map.get(p, [])
        embedding_available = bool(embed_keys and any(os.getenv(k) for k in embed_keys))
        info = get_provider_info(p)
        info["embedding_available"] = embedding_available
        results.append(info)

    return results
