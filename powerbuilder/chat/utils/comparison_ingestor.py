"""
chat/utils/comparison_ingestor.py

Re-ingests documents from the primary OpenAI Pinecone index into each
provider-specific comparison index using that provider's native embedding model.

After running this script all comparison indexes contain the identical set of
documents.  The only variable between indexes is the embedding model, which is
exactly what test_llm_comparison.py measures.

Usage:
    python -m chat.utils.comparison_ingestor            # all configured providers
    python -m chat.utils.comparison_ingestor --provider gemini
    python -m chat.utils.comparison_ingestor --dry-run

What it does:
  1. Reads every vector+metadata chunk from the source OpenAI index
     (OPENAI_PINECONE_INDEX_NAME env var, default "openai-research-index")
     using Pinecone's list/fetch API to get the original text back.
  2. For each provider in DEFAULT_PROVIDERS (gemini, cohere, anthropic):
       - gemini and cohere use their native embedding models.
       - anthropic has no native embedding API, so it uses OpenAI
         text-embedding-3-small.  Its index (powerbuilder-anthropic) is
         therefore in the same 1536-dim OpenAI embedding space, which means
         the comparison for anthropic is completion quality only, not
         retrieval quality.
     For each target it creates the Pinecone index if it does not exist,
     then re-embeds all chunks and upserts them in batches.
  3. Skips providers where the target index already has vectors unless
     --force is passed.
  4. mistral is excluded — no Pinecone slot is allocated for it.

Requirements:
  - PINECONE_API_KEY: Pinecone access
  - Provider API keys for any provider you want to index

  Index names are read from environment variables following the convention
  {PROVIDER_NAME}_PINECONE_INDEX_NAME (matching the existing codebase pattern):

    OPENAI_PINECONE_INDEX_NAME    source index + OpenAI comparison index
    ANTHROPIC_PINECONE_INDEX_NAME target for anthropic (shares OpenAI index if unset)
    GOOGLEAI_PINECONE_INDEX_NAME  target for gemini
    LLAMA_PINECONE_INDEX_NAME     target for llama
    MISTRAL_PINECONE_INDEX_NAME   target for mistral
    COHERE_PINECONE_INDEX_NAME    target for cohere
    GROQ_PINECONE_INDEX_NAME      target for groq (shares OpenAI index if unset)

Note: Pinecone Serverless indexes on the free tier are limited to 5 total.
      Run with --dry-run first to see which providers would be created.
"""

import argparse
import os
import sys
import time

from dotenv import load_dotenv
load_dotenv()

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from chat.utils.llm_config import (
    EMBEDDING_DIMENSIONS,
    PINECONE_INDEX_NAMES,
    EmbeddingConfig,
    get_configured_providers,
    get_embedding_client,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SOURCE_INDEX     = os.getenv("OPENAI_PINECONE_INDEX_NAME", "openai-research-index")
SOURCE_NAMESPACE = ""          # Pinecone default namespace (empty string)
BATCH_SIZE       = 96          # vectors per upsert call — Pinecone limit is 100
FETCH_BATCH      = 200         # IDs per fetch call
INDEX_WAIT_SECS  = 60          # seconds to wait for a newly created index to be ready

# Providers to index by default (no --provider flag given).
# - gemini and cohere: use native embeddings → dedicated comparison indexes.
# - anthropic: no native embeddings → uses OpenAI embeddings, comparison is
#   completion quality only.
# - mistral excluded: no Pinecone slot allocated.
# - openai excluded: it is the source index, already indexed.
# - groq/llama excluded: no keys configured.
DEFAULT_PROVIDERS = ["gemini", "cohere", "anthropic"]


# ---------------------------------------------------------------------------
# Pinecone helpers
# ---------------------------------------------------------------------------

def _get_pinecone():
    from pinecone import Pinecone
    key = os.getenv("PINECONE_API_KEY")
    if not key:
        raise RuntimeError("PINECONE_API_KEY is not set.")
    return Pinecone(api_key=key)


def _index_exists(pc, name: str) -> bool:
    return any(idx.name == name for idx in pc.list_indexes())


def _create_index_if_needed(pc, name: str, dimensions: int, dry_run: bool) -> bool:
    """
    Create a Serverless cosine index if it does not exist.
    Returns True if the index is ready to use, False if skipped (dry_run).
    """
    if _index_exists(pc, name):
        print(f"    Index '{name}' already exists.")
        return True

    if dry_run:
        print(f"    [DRY RUN] Would create index '{name}' ({dimensions} dims, cosine).")
        return False

    from pinecone import ServerlessSpec
    print(f"    Creating index '{name}' ({dimensions} dims, cosine)...", flush=True)
    pc.create_index(
        name=name,
        dimension=dimensions,
        metric="cosine",
        spec=ServerlessSpec(cloud="aws", region="us-east-1"),
    )
    # Wait for the index to become ready
    deadline = time.time() + INDEX_WAIT_SECS
    while time.time() < deadline:
        info = pc.describe_index(name)
        if getattr(info.status, "ready", False):
            print(f"    Index '{name}' is ready.")
            return True
        time.sleep(3)

    raise TimeoutError(f"Index '{name}' was not ready within {INDEX_WAIT_SECS}s.")


def _count_vectors(pc, index_name: str, namespace: str = "") -> int:
    """Return the vector count for a namespace (0 if index does not exist)."""
    if not _index_exists(pc, index_name):
        return 0
    try:
        idx   = pc.Index(index_name)
        stats = idx.describe_index_stats()
        ns    = stats.namespaces or {}
        entry = ns.get(namespace) or ns.get("__default__")
        return getattr(entry, "vector_count", 0) if entry else 0
    except Exception:
        return 0


# ---------------------------------------------------------------------------
# Source document fetching
# ---------------------------------------------------------------------------

def fetch_source_chunks(pc, source_index: str, namespace: str = "") -> list[dict]:
    """
    Fetch all chunks from the source Pinecone index.

    Uses list() to get vector IDs then fetch() to retrieve text+metadata.
    Returns a list of dicts: {"id": str, "text": str, "metadata": dict}.
    """
    print(f"  Fetching chunks from source index '{source_index}' "
          f"namespace='{namespace or '(default)'}' ...", flush=True)

    index   = pc.Index(source_index)
    chunks  = []
    id_buf: list[str] = []

    def _flush_buf():
        if not id_buf:
            return
        resp = index.fetch(ids=id_buf, namespace=namespace)
        for vid, vec in (resp.vectors or {}).items():
            meta = dict(vec.metadata or {})
            text = meta.get("text", "")
            if text:
                chunks.append({"id": vid, "text": text, "metadata": meta})
        id_buf.clear()

    # list() yields one page of IDs at a time
    for id_batch in index.list(namespace=namespace):
        id_buf.extend(id_batch)
        if len(id_buf) >= FETCH_BATCH:
            _flush_buf()

    _flush_buf()  # remainder

    print(f"  Fetched {len(chunks)} chunks with text content.")
    return chunks


# ---------------------------------------------------------------------------
# Re-ingestion
# ---------------------------------------------------------------------------

def _embed_and_upsert(
    pc,
    chunks:     list[dict],
    emb_cfg:    EmbeddingConfig,
    target_idx: str,
    namespace:  str = "",
) -> int:
    """
    Embed *chunks* using emb_cfg and upsert into *target_idx*.
    Returns the number of vectors upserted.
    """
    from langchain_pinecone import PineconeVectorStore
    from langchain_core.documents import Document as LCDocument

    index = pc.Index(target_idx)
    total = 0

    for i in range(0, len(chunks), BATCH_SIZE):
        batch = chunks[i : i + BATCH_SIZE]
        docs  = [
            LCDocument(
                page_content=c["text"],
                metadata={k: v for k, v in c["metadata"].items() if k != "text"},
            )
            for c in batch
        ]
        PineconeVectorStore.from_documents(
            documents=docs,
            embedding=emb_cfg.client,
            index_name=target_idx,
            namespace=namespace,
        )
        total += len(batch)
        print(f"    Upserted {total}/{len(chunks)} vectors...", end="\r", flush=True)

    print()  # newline after the progress line
    return total


def ingest_provider(
    pc,
    provider:  str,
    chunks:    list[dict],
    force:     bool = False,
    dry_run:   bool = False,
) -> dict:
    """
    Re-embed *chunks* into the provider-specific Pinecone index.

    Returns a result dict with keys: provider, index_name, status, vectors_upserted.
    """
    result = {"provider": provider, "index_name": "", "status": "skipped", "vectors_upserted": 0}

    # Build embedding config — raises RuntimeError if key is missing
    try:
        emb_cfg = get_embedding_client(provider=provider)
    except RuntimeError as e:
        result["status"] = f"skipped (no API key: {e})"
        return result

    target_index = emb_cfg.index_name
    dimensions   = emb_cfg.dimensions
    result["index_name"] = target_index

    print(f"\n[{provider}]  index='{target_index}'  "
          f"model='{emb_cfg.model}'  dims={dimensions}")

    # Skip if already indexed (unless force)
    if not force:
        count = _count_vectors(pc, target_index)
        if count > 0:
            print(f"  Already has {count} vectors. Use --force to re-index.")
            result["status"] = f"already_indexed ({count} vectors)"
            return result

    # Create index if needed
    ready = _create_index_if_needed(pc, target_index, dimensions, dry_run)
    if not ready:
        result["status"] = "dry_run"
        return result

    if dry_run:
        result["status"] = "dry_run"
        return result

    # Smoke test — embed one chunk and verify dimensions before committing to the
    # full batch.  This catches model-name 404s and dimension mismatches early.
    print(f"  Smoke test: embedding 1 chunk with '{emb_cfg.model}'...", flush=True)
    try:
        sample_vec = emb_cfg.client.embed_query(chunks[0]["text"])
    except Exception as e:
        result["status"] = f"smoke_test_failed ({e})"
        print(f"  Smoke test FAILED: {e}")
        return result

    actual_dims = len(sample_vec)
    if actual_dims != dimensions:
        result["status"] = (
            f"smoke_test_failed (expected {dimensions} dims, got {actual_dims}). "
            f"Update EMBEDDING_DIMENSIONS['{provider}'] or point "
            f"'{target_index}' at a {actual_dims}-dim index."
        )
        print(f"  Smoke test FAILED: {result['status']}")
        return result

    print(f"  Smoke test passed ({actual_dims} dims). Proceeding with full upsert.")

    # Embed + upsert
    print(f"  Re-embedding {len(chunks)} chunks with '{emb_cfg.model}'...")
    upserted = _embed_and_upsert(pc, chunks, emb_cfg, target_index)
    result["status"]           = "ok"
    result["vectors_upserted"] = upserted
    print(f"  Done. {upserted} vectors upserted.")
    return result


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run(
    providers:  list[str] | None = None,
    force:      bool = False,
    dry_run:    bool = False,
    source_idx: str  = SOURCE_INDEX,
) -> list[dict]:
    """
    Re-ingest source documents into all (or specified) provider indexes.

    Args:
        providers:  List of provider names to process. None = all configured
                    providers that have native embedding support.
        force:      Re-index even if the target index already has vectors.
        dry_run:    Print plan without making any API calls.
        source_idx: Source Pinecone index to read from.

    Returns:
        List of result dicts (one per provider attempted).
    """
    pc = _get_pinecone()

    # Resolve which providers to process
    configured  = get_configured_providers()
    target_list = [x.lower() for x in providers] if providers else DEFAULT_PROVIDERS
    targets     = [p for p in configured if p["provider"] in target_list]

    if not targets:
        print(f"None of {target_list} are configured. Check your API keys.")
        return []

    print(f"Providers to index: {[t['provider'] for t in targets]}")
    print(f"Source index: '{source_idx}'")
    if dry_run:
        print("[DRY RUN MODE — no writes will be made]\n")

    # Fetch source chunks once — shared across all providers
    chunks = fetch_source_chunks(pc, source_idx)
    if not chunks:
        print("No chunks found in source index. Run bulk_upload.py first.")
        return []

    results = []
    for target in targets:
        res = ingest_provider(pc, target["provider"], chunks, force=force, dry_run=dry_run)
        results.append(res)

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    for r in results:
        print(f"  {r['provider']:12} {r['index_name']:30} {r['status']}")

    return results


if __name__ == "__main__":
    ap = argparse.ArgumentParser(
        description="Re-ingest Pinecone source documents into provider-specific indexes."
    )
    ap.add_argument(
        "--provider", "-p",
        nargs="+",
        metavar="PROVIDER",
        help="Specific provider(s) to index (default: all configured with native embeddings).",
    )
    ap.add_argument(
        "--force",
        action="store_true",
        help="Re-index even if the target index already has vectors.",
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Print plan without making any API calls or writes.",
    )
    ap.add_argument(
        "--source",
        default=SOURCE_INDEX,
        help=f"Source Pinecone index (default: {SOURCE_INDEX}).",
    )
    args = ap.parse_args()
    run(providers=args.provider, force=args.force, dry_run=args.dry_run, source_idx=args.source)
