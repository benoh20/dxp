"""
chat/utils/llm_config.py

Central LLM configuration for Powerbuilder.

Usage:
    from chat.utils.llm_config import get_completion_client, get_embedding_client

The active provider is controlled by the LLM_PROVIDER environment variable
(default: "openai"). Embeddings are always OpenAI text-embedding-3-small
regardless of provider, because Pinecone compatibility requires a fixed
embedding space.

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
from typing import Callable

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

# Default model for each built-in provider
_DEFAULT_MODELS: dict[str, str] = {
    "openai":    "gpt-4o",
    "anthropic": "claude-sonnet-4-5",
    "gemini":    "gemini-1.5-pro",
    "llama":     "llama-3.1-70b-versatile",
    "mistral":   "mistral-large-latest",
    "cohere":    "command-r-plus",
    "groq":      "llama-3.1-70b-versatile",
}

# Registry for custom providers added via register_custom_provider().
# Maps provider name → callable() that returns a LangChain chat model.
_custom_registry: dict[str, Callable] = {}

# ---------------------------------------------------------------------------
# Active provider
# ---------------------------------------------------------------------------

LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "openai").lower().strip()


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

    Example:
        from chat.utils.llm_config import register_custom_provider
        from langchain_openai import ChatOpenAI

        register_custom_provider(
            "my_provider",
            lambda: ChatOpenAI(model="gpt-4o-mini", temperature=0),
        )

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
        temperature: Sampling temperature passed to the underlying model.
        provider:    Override the global LLM_PROVIDER for this call.

    Returns:
        A LangChain-compatible chat model with a .invoke() / .stream() interface.

    Raises:
        ValueError:   Unknown provider name.
        ImportError:  Required langchain-* package not installed.
        RuntimeError: Required API key environment variable is missing.
    """
    active = (provider or LLM_PROVIDER).lower().strip()

    # --- Custom providers registered via register_custom_provider() ----------
    if active in _custom_registry:
        return _custom_registry[active]()

    # --- Built-in providers --------------------------------------------------
    if active == "openai":
        from langchain_openai import ChatOpenAI
        key = os.getenv("OPENAI_API_KEY")
        if not key:
            raise RuntimeError("LLM_PROVIDER=openai but OPENAI_API_KEY is not set.")
        return ChatOpenAI(
            model=_DEFAULT_MODELS["openai"],
            temperature=temperature,
            openai_api_key=key,
        )

    if active == "anthropic":
        from langchain_anthropic import ChatAnthropic
        key = os.getenv("ANTHROPIC_API_KEY")
        if not key:
            raise RuntimeError("LLM_PROVIDER=anthropic but ANTHROPIC_API_KEY is not set.")
        return ChatAnthropic(
            model=_DEFAULT_MODELS["anthropic"],
            temperature=temperature,
            anthropic_api_key=key,
        )

    if active == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI
        key = os.getenv("GOOGLE_API_KEY")
        if not key:
            raise RuntimeError("LLM_PROVIDER=gemini but GOOGLE_API_KEY is not set.")
        return ChatGoogleGenerativeAI(
            model=_DEFAULT_MODELS["gemini"],
            temperature=temperature,
            google_api_key=key,
        )

    if active == "llama":
        # Prefer Groq for llama (fast inference); fall back to Together.ai
        groq_key  = os.getenv("GROQ_API_KEY")
        llama_key = os.getenv("LLAMA_API_KEY")
        if groq_key:
            from langchain_groq import ChatGroq
            return ChatGroq(
                model=_DEFAULT_MODELS["llama"],
                temperature=temperature,
                groq_api_key=groq_key,
            )
        if llama_key:
            # Together.ai uses the OpenAI-compatible API surface
            from langchain_openai import ChatOpenAI
            return ChatOpenAI(
                model=_DEFAULT_MODELS["llama"],
                temperature=temperature,
                openai_api_key=llama_key,
                openai_api_base="https://api.together.xyz/v1",
            )
        raise RuntimeError(
            "LLM_PROVIDER=llama but neither GROQ_API_KEY nor LLAMA_API_KEY is set."
        )

    if active == "mistral":
        from langchain_mistralai import ChatMistralAI
        key = os.getenv("MISTRAL_API_KEY")
        if not key:
            raise RuntimeError("LLM_PROVIDER=mistral but MISTRAL_API_KEY is not set.")
        return ChatMistralAI(
            model=_DEFAULT_MODELS["mistral"],
            temperature=temperature,
            mistral_api_key=key,
        )

    if active == "cohere":
        from langchain_cohere import ChatCohere
        key = os.getenv("COHERE_API_KEY")
        if not key:
            raise RuntimeError("LLM_PROVIDER=cohere but COHERE_API_KEY is not set.")
        return ChatCohere(
            model=_DEFAULT_MODELS["cohere"],
            temperature=temperature,
            cohere_api_key=key,
        )

    if active == "groq":
        from langchain_groq import ChatGroq
        key = os.getenv("GROQ_API_KEY")
        if not key:
            raise RuntimeError("LLM_PROVIDER=groq but GROQ_API_KEY is not set.")
        return ChatGroq(
            model=_DEFAULT_MODELS["groq"],
            temperature=temperature,
            groq_api_key=key,
        )

    raise ValueError(
        f"Unknown LLM provider: '{active}'. "
        f"Supported: {SUPPORTED_PROVIDERS}. "
        "Use register_custom_provider() to add a new one."
    )


# ---------------------------------------------------------------------------
# Embedding client (always OpenAI — locked for Pinecone compatibility)
# ---------------------------------------------------------------------------

def get_embedding_client(model: str = "text-embedding-3-small"):
    """
    Return an OpenAI embedding client regardless of the active LLM_PROVIDER.

    Pinecone indexes are built against a specific embedding space. Switching
    the embedding model would make all existing vectors unsearchable, so
    embeddings are intentionally locked to OpenAI text-embedding-3-small.

    Args:
        model: Override the embedding model name if needed (rare).

    Returns:
        A LangChain OpenAIEmbeddings instance.
    """
    from langchain_openai import OpenAIEmbeddings
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        raise RuntimeError(
            "OPENAI_API_KEY is required for embeddings regardless of LLM_PROVIDER."
        )
    return OpenAIEmbeddings(model=model, openai_api_key=key)


# ---------------------------------------------------------------------------
# Introspection helpers
# ---------------------------------------------------------------------------

def get_provider_info(provider: str | None = None) -> dict:
    """
    Return the active provider name and its default model for logging.

    Args:
        provider: Override the global LLM_PROVIDER for this lookup.

    Returns:
        {"provider": str, "model": str}

    Example:
        >>> get_provider_info()
        {"provider": "openai", "model": "gpt-4o"}
    """
    active = (provider or LLM_PROVIDER).lower().strip()
    model  = _DEFAULT_MODELS.get(active, "custom")
    return {"provider": active, "model": model}
