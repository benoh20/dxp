# powerbuilder/chat/agents/researcher.py
import hashlib
import logging
import os
from datetime import datetime
from typing import Optional

from dotenv import load_dotenv
load_dotenv()

from langchain_pinecone import PineconeVectorStore
from ..utils.llm_config import get_embedding_client

from .state import AgentState

# django.setup() was previously called here at module level. That causes
# AppRegistryNotReady errors when this module is imported before Django is
# initialised (e.g. during testing or LangGraph graph construction). The
# correct home for one-time Django initialisation is AppConfig.ready() in
# chat/apps.py, which Django calls automatically after all apps are loaded.
# For standalone scripts or management commands, call django.setup() explicitly
# in that script's __main__ block — not inside a shared module.

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Central config
# ---------------------------------------------------------------------------

# Embedding model used for Pinecone queries. Defined here as a single source
# of truth so it can be swapped in one place when multi-LLM support is added.
# Move to chat/config.py alongside LLM model names when that module is created.
# Override at runtime via the EMBEDDING_MODEL environment variable if needed.
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")

# Number of results to retrieve per namespace. Kept low by default so the
# synthesizer receives a focused, high-quality context window.
DEFAULT_K = 5

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_date(date_val) -> Optional[datetime]:
    """
    Parse a metadata date value into a datetime for recency sorting.
    Tries common formats found in political research PDFs.
    Returns None for unparseable values so those documents sort last.
    """
    if not date_val:
        return None
    if isinstance(date_val, datetime):
        return date_val
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y", "%B %Y", "%b %Y", "%B %d, %Y", "%Y"):
        try:
            return datetime.strptime(str(date_val).strip(), fmt)
        except ValueError:
            continue
    return None


def _content_hash(text: str) -> str:
    """SHA-256 hash of document content for cross-namespace deduplication."""
    return hashlib.sha256(text.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Node
# ---------------------------------------------------------------------------

def research_node(state: AgentState, k: int = DEFAULT_K) -> dict:
    """
    Dual-namespace Pinecone search agent.

    Searches both the general (__default__) and org-specific namespaces,
    deduplicates results across namespaces by content hash, sorts by document
    recency, and formats each result with source and date for the synthesizer.

    The core dual-namespace search logic is intentionally preserved unchanged.
    """
    query         = state["query"]
    org_namespace = state.get("org_namespace", "general")

    embeddings = get_embedding_client(model=EMBEDDING_MODEL)
    index_name = os.getenv("OPENAI_PINECONE_INDEX_NAME")

    logger.debug(f"Searching index '{index_name}' | org: '{org_namespace}' | k={k}")

    # Core dual-namespace search — do not change
    general_store = PineconeVectorStore(
        index_name=index_name,
        embedding=embeddings,
        namespace="__default__",
        text_key="text",
    )
    general_docs = general_store.similarity_search(query, k=k)

    logger.debug(f"Found {len(general_docs)} documents in general namespace.")

    org_docs = []
    if org_namespace and org_namespace != "general":
        org_store = PineconeVectorStore(
            index_name=index_name,
            embedding=embeddings,
            namespace=org_namespace,
            text_key="text",
        )
        org_docs = org_store.similarity_search(query, k=k)

        logger.debug(f"Found {len(org_docs)} documents in org namespace '{org_namespace}'.")

    # Deduplicate across namespaces by content hash.
    # The same chunk can appear in both __default__ and an org namespace if a
    # document was uploaded to both. Keep the first occurrence (general first).
    seen_hashes: set = set()
    unique_docs = []
    for doc in (general_docs + org_docs):
        h = _content_hash(doc.page_content)
        if h not in seen_hashes:
            seen_hashes.add(h)
            unique_docs.append(doc)

    logger.debug(
        f"{len(unique_docs)} unique chunks after deduplication "
        f"(dropped {len(general_docs) + len(org_docs) - len(unique_docs)} duplicates)."
    )

    # Sort by recency — most recent documents first, undated documents last.
    # Recency signals relevance for political research: a 2025 poll supersedes
    # a 2019 poll on the same topic even if the vector similarity scores are close.
    unique_docs.sort(
        key=lambda d: _parse_date(d.metadata.get("date")) or datetime.min,
        reverse=True,
    )

    # Format for the synthesizer. Include source and date so the synthesizer
    # can communicate research recency to the user in the final answer.
    formatted_findings = []
    for doc in unique_docs:
        source   = doc.metadata.get("source", "General Knowledge")
        date_raw = doc.metadata.get("date")
        date_str = str(date_raw).strip() if date_raw else "date unknown"
        memo = (
            f"--- MEMO FROM SOURCE: {source} | DATE: {date_str} ---\n"
            f"{doc.page_content}\n"
        )
        formatted_findings.append(memo)

    return {
        "research_results": formatted_findings,
        "active_agents":    ["researcher"],
    }


# ---------------------------------------------------------------------------
# Local testing
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # When running this file directly, Django must be set up before import.
    # This is the correct place for django.setup() in a standalone script.
    import django
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "powerbuilder_app.settings")
    django.setup()

    test_state = {
        "query":         "What does the research say about young voters?",
        "org_namespace": "boh_key",
    }
    result = research_node(test_state)
    print(f"Retrieved {len(result['research_results'])} chunks.")
