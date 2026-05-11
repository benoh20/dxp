# powerbuilder/chat/agents/researcher.py
import hashlib
import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
load_dotenv()

from langchain_pinecone import PineconeVectorStore
from ..utils.llm_config import get_embedding_client, COMPARISON_MODE, LLM_PROVIDER

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

# Path to the local corpus index file produced by scripts/seed_best_practices.py.
# When Pinecone is unreachable, or USE_LOCAL_CORPUS=true, the researcher reads
# from this file and does keyword scoring against it instead. This is what
# makes the demo run on a laptop with no Pinecone account.
LOCAL_CORPUS_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "scripts"
    / ".local_corpus_index.json"
)

# ---------------------------------------------------------------------------
# Geographic lookups (copied from opposition_research.py — avoids circular import)
# ---------------------------------------------------------------------------

_FIPS_TO_STATE_ABBR: dict[str, str] = {
    "01": "AL", "02": "AK", "04": "AZ", "05": "AR", "06": "CA",
    "08": "CO", "09": "CT", "10": "DE", "11": "DC", "12": "FL",
    "13": "GA", "15": "HI", "16": "ID", "17": "IL", "18": "IN",
    "19": "IA", "20": "KS", "21": "KY", "22": "LA", "23": "ME",
    "24": "MD", "25": "MA", "26": "MI", "27": "MN", "28": "MS",
    "29": "MO", "30": "MT", "31": "NE", "32": "NV", "33": "NH",
    "34": "NJ", "35": "NM", "36": "NY", "37": "NC", "38": "ND",
    "39": "OH", "40": "OK", "41": "OR", "42": "PA", "44": "RI",
    "45": "SC", "46": "SD", "47": "TN", "48": "TX", "49": "UT",
    "50": "VT", "51": "VA", "53": "WA", "54": "WV", "55": "WI",
    "56": "WY",
}

_STATE_ABBR_TO_NAME: dict[str, str] = {
    "AL": "Alabama",        "AK": "Alaska",         "AZ": "Arizona",
    "AR": "Arkansas",       "CA": "California",     "CO": "Colorado",
    "CT": "Connecticut",    "DE": "Delaware",        "DC": "District of Columbia",
    "FL": "Florida",        "GA": "Georgia",         "HI": "Hawaii",
    "ID": "Idaho",          "IL": "Illinois",        "IN": "Indiana",
    "IA": "Iowa",           "KS": "Kansas",          "KY": "Kentucky",
    "LA": "Louisiana",      "ME": "Maine",           "MD": "Maryland",
    "MA": "Massachusetts",  "MI": "Michigan",        "MN": "Minnesota",
    "MS": "Mississippi",    "MO": "Missouri",        "MT": "Montana",
    "NE": "Nebraska",       "NV": "Nevada",          "NH": "New Hampshire",
    "NJ": "New Jersey",     "NM": "New Mexico",      "NY": "New York",
    "NC": "North Carolina", "ND": "North Dakota",    "OH": "Ohio",
    "OK": "Oklahoma",       "OR": "Oregon",          "PA": "Pennsylvania",
    "RI": "Rhode Island",   "SC": "South Carolina",  "SD": "South Dakota",
    "TN": "Tennessee",      "TX": "Texas",           "UT": "Utah",
    "VT": "Vermont",        "VA": "Virginia",        "WA": "Washington",
    "WV": "West Virginia",  "WI": "Wisconsin",       "WY": "Wyoming",
}

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
# Local fallback search
# ---------------------------------------------------------------------------

_TOKEN_RE = re.compile(r"[a-zA-ZÀ-ÿ0-9]+")

# Common stopwords filtered before scoring. Kept small and explicit so the
# behaviour is auditable. We intentionally keep terms like "latinx", "gotv",
# "spanish", "gwinnett", and other domain-specific tokens.
_STOPWORDS = frozenset({
    "the", "a", "an", "and", "or", "of", "for", "in", "on", "to", "with",
    "is", "are", "be", "by", "at", "from", "that", "this", "it", "as",
    "what", "how", "why", "who", "when", "where", "do", "does",
    "i", "we", "our", "you", "your", "me", "my",
})

_local_corpus_cache: Optional[list[dict]] = None


def _load_local_corpus() -> list[dict]:
    """
    Read the local corpus index from disk and cache it for the process lifetime.

    Returns an empty list if the file does not exist, so the researcher can
    degrade gracefully rather than crash when running on a freshly-cloned
    checkout that has not yet seeded the corpus.
    """
    global _local_corpus_cache
    if _local_corpus_cache is not None:
        return _local_corpus_cache

    if not LOCAL_CORPUS_PATH.exists():
        logger.warning(
            f"Local corpus index not found at {LOCAL_CORPUS_PATH}. "
            f"Run `python scripts/seed_best_practices.py --local-only` to generate it."
        )
        _local_corpus_cache = []
        return _local_corpus_cache

    try:
        payload = json.loads(LOCAL_CORPUS_PATH.read_text(encoding="utf-8"))
        _local_corpus_cache = payload.get("chunks", [])
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning(f"Failed to load local corpus: {exc}")
        _local_corpus_cache = []

    return _local_corpus_cache


def _tokenize(text: str) -> set[str]:
    """Lowercase, alphanumeric tokens with stopwords removed."""
    return {
        tok.lower() for tok in _TOKEN_RE.findall(text)
        if tok.lower() not in _STOPWORDS and len(tok) > 2
    }


def _score_chunk(query_tokens: set[str], chunk: dict) -> float:
    """
    Score a corpus chunk against the query.

    Three signals, weighted:
    - Tag overlap (highest weight, 3x): tags are curator-applied semantic labels.
    - Title overlap (2x): title is hand-written and high-signal.
    - Body overlap (1x): substring presence per query token.
    """
    if not query_tokens:
        return 0.0

    score = 0.0
    meta = chunk.get("metadata", {})

    tags = meta.get("tags") or []
    if isinstance(tags, list):
        tag_set = {str(t).lower() for t in tags}
        score += 3.0 * len(query_tokens & tag_set)

    title_tokens = _tokenize(str(meta.get("title", "")))
    score += 2.0 * len(query_tokens & title_tokens)

    body_lower = chunk.get("text", "").lower()
    score += sum(1 for tok in query_tokens if tok in body_lower)

    return score


def _local_corpus_search(query: str, k: int) -> list[dict]:
    """
    Keyword-score the local corpus and return the top-k chunks shaped to look
    like LangChain Document objects (page_content + metadata).
    """
    corpus = _load_local_corpus()
    if not corpus:
        return []

    query_tokens = _tokenize(query)
    scored = [(_score_chunk(query_tokens, c), c) for c in corpus]
    scored = [(s, c) for s, c in scored if s > 0]
    scored.sort(key=lambda pair: pair[0], reverse=True)

    # Wrap top-k chunks in objects with the same shape PineconeVectorStore returns.
    class _LocalDoc:
        def __init__(self, text: str, metadata: dict):
            self.page_content = text
            self.metadata = metadata

    return [_LocalDoc(c["text"], c.get("metadata", {})) for _, c in scored[:k]]


def _use_local_corpus() -> bool:
    """Whether to skip Pinecone and read from the local corpus index."""
    flag = os.getenv("USE_LOCAL_CORPUS", "").strip().lower()
    return flag in {"1", "true", "yes", "on"}


# ---------------------------------------------------------------------------
# Two-pass tiered retrieval helpers
# ---------------------------------------------------------------------------

def _build_focused_query(state: AgentState) -> Optional[str]:
    """
    Build a geographically and demographically focused re-ranking query from
    AgentState context populated by earlier nodes (precincts, win_number, etc.).

    Returns None when there is insufficient context to improve on the raw query
    (no state_fips in structured_data AND no demographic_intent set), which
    causes the caller to fall back to single-pass MMR.
    """
    structured_data    = state.get("structured_data") or []
    demographic_intent = (state.get("demographic_intent") or "").strip()
    original_query     = (state.get("query") or "").strip()

    state_fips    = None
    district_type = None
    for entry in structured_data:
        fips = entry.get("state_fips")
        if fips:
            state_fips    = str(fips).zfill(2)
            district_type = entry.get("district_type")
            break

    if not state_fips and not demographic_intent:
        return None

    parts = [original_query]

    if state_fips:
        abbr       = _FIPS_TO_STATE_ABBR.get(state_fips, "")
        state_name = _STATE_ABBR_TO_NAME.get(abbr, "")
        if state_name:
            parts.append(state_name)

    if demographic_intent:
        # "youth+hispanic" → "youth hispanic voters"
        parts.append(demographic_intent.replace("+", " ") + " voters")

    if district_type:
        parts.append(district_type.replace("_", " "))

    focused = " ".join(p for p in parts if p).strip()
    return focused if focused != original_query else None


def _two_pass_search(
    store: "PineconeVectorStore",
    query: str,
    focused_query: str,
    embeddings,
    k: int = 10,
) -> list:
    """
    Two-pass tiered retrieval for a single Pinecone namespace.

    Pass 1 — Broad: similarity_search top 50 docs using the original query.
    Pass 2 — Focused: re-rank those 50 docs by cosine similarity against the
              focused query embedding; keep top 20.
    Final   — MMR over the top 20 with lambda_mult=0.5; return k diverse docs.

    Raises on any failure so the caller can fall back to single-pass MMR.
    """
    import numpy as np
    try:
        from langchain_core.vectorstores.utils import maximal_marginal_relevance
    except ImportError:
        from langchain.vectorstores.utils import maximal_marginal_relevance

    # Pass 1: broad similarity pool
    pass1_with_scores = store.similarity_search_with_score(query, k=50)
    pass1_docs = [doc for doc, _ in pass1_with_scores]

    if not pass1_docs:
        return []

    # Embed original query (for MMR relevance), focused query (for re-ranking),
    # and all pass1 doc texts (for cosine scoring against focused query).
    query_emb   = np.array(embeddings.embed_query(query))
    focused_emb = np.array(embeddings.embed_query(focused_query))
    doc_emb_mat = np.array(
        embeddings.embed_documents([d.page_content for d in pass1_docs])
    )  # shape: (len(pass1_docs), embedding_dim)

    # Pass 2: cosine similarity of each doc against the focused query
    focused_norm = np.linalg.norm(focused_emb)
    doc_norms    = np.linalg.norm(doc_emb_mat, axis=1)
    focused_sims = (doc_emb_mat @ focused_emb) / (doc_norms * focused_norm + 1e-10)

    # Top 20 by focused similarity
    top20_idx  = np.argsort(focused_sims)[::-1][:20]
    top20_docs = [pass1_docs[i] for i in top20_idx]
    top20_embs = [doc_emb_mat[i].tolist() for i in top20_idx]

    # MMR over the 20 candidates — relevance scored against original query
    mmr_idx = maximal_marginal_relevance(
        query_emb,
        top20_embs,
        lambda_mult=0.5,
        k=min(k, len(top20_docs)),
    )
    final_docs = [top20_docs[i] for i in mmr_idx]

    logger.info(
        "Researcher pass 1: %d docs, pass 2 focused query: '%s', final: %d docs",
        len(pass1_docs), focused_query, len(final_docs),
    )
    return final_docs


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

    # Local fallback path: explicitly opted in via USE_LOCAL_CORPUS, or a
    # missing PINECONE_API_KEY (a freshly-cloned dev checkout). The local
    # corpus has only the curated best-practices set, so we treat its results
    # as the general-namespace stand-in and skip the org namespace.
    if _use_local_corpus() or not os.getenv("PINECONE_API_KEY"):
        logger.info("Researcher using local corpus fallback (no Pinecone).")
        general_docs = _local_corpus_search(query, k=10)
        org_docs = []
        return _format_results(general_docs, org_docs)

    # In comparison mode, route to the active provider's native embedding model
    # and its dedicated Pinecone index.  In normal mode, always use OpenAI
    # embeddings and the production index regardless of LLM_PROVIDER.
    try:
        emb_cfg    = get_embedding_client(provider=LLM_PROVIDER if COMPARISON_MODE else None)
        embeddings = emb_cfg.client
        index_name = emb_cfg.index_name

        logger.debug(
            f"Searching index '{index_name}' | provider: '{emb_cfg.provider}' "
            f"| model: '{emb_cfg.model}' | comparison_mode: {COMPARISON_MODE} "
            f"| org: '{org_namespace}' | k={k}"
        )

        # Build focused query for two-pass retrieval (None → single-pass fallback)
        focused_query = _build_focused_query(state) if not COMPARISON_MODE else None

        # Core dual-namespace search — do not change shape or deduplication logic
        general_store = PineconeVectorStore(
            index_name=index_name,
            embedding=embeddings,
            namespace="__default__",
            text_key="text",
        )

        if focused_query:
            try:
                general_docs = _two_pass_search(general_store, query, focused_query, embeddings, k=10)
            except Exception as tp_exc:
                logger.warning(
                    "Two-pass retrieval failed for general namespace (%s); "
                    "falling back to single-pass MMR.", tp_exc,
                )
                general_docs = general_store.max_marginal_relevance_search(query, k=10, fetch_k=100)
        else:
            general_docs = general_store.max_marginal_relevance_search(query, k=10, fetch_k=100)

        logger.debug(f"Found {len(general_docs)} documents in general namespace.")

        org_docs = []
        if org_namespace and org_namespace != "general":
            org_store = PineconeVectorStore(
                index_name=index_name,
                embedding=embeddings,
                namespace=org_namespace,
                text_key="text",
            )

            if focused_query:
                try:
                    org_docs = _two_pass_search(org_store, query, focused_query, embeddings, k=10)
                except Exception as tp_exc:
                    logger.warning(
                        "Two-pass retrieval failed for org namespace '%s' (%s); "
                        "falling back to single-pass MMR.", org_namespace, tp_exc,
                    )
                    org_docs = org_store.max_marginal_relevance_search(query, k=10, fetch_k=100)
            else:
                org_docs = org_store.max_marginal_relevance_search(query, k=10, fetch_k=100)

            logger.debug(f"Found {len(org_docs)} documents in org namespace '{org_namespace}'.")
    except Exception as exc:
        # Pinecone or embedding-provider unreachable: degrade to local corpus
        # so the demo still produces a grounded answer.
        logger.warning(f"Pinecone/embedding lookup failed ({exc}); using local corpus fallback.")
        general_docs = _local_corpus_search(query, k=10)
        org_docs = []
        return _format_results(general_docs, org_docs)

    return _format_results(general_docs, org_docs)


def _format_results(general_docs: list, org_docs: list) -> dict:
    """
    Deduplicate, sort by recency, and format documents for the synthesizer.

    Extracted into a helper so both the Pinecone path and the local-corpus
    fallback path produce identical output shapes.
    """
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

    # Sort by recency, most recent documents first, undated documents last.
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
