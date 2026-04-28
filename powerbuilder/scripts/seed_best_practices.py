"""
Seed the best-practices corpus into Pinecone (__default__ namespace).

Reads every .md file under tool_templates/best_practices/, extracts metadata
from the YAML-style frontmatter (title, source, date, document_type, tags),
chunks the body, and upserts to the OPENAI_PINECONE_INDEX_NAME index with
deterministic vector IDs so re-running the script is idempotent.

Usage (from /powerbuilder):
    python scripts/seed_best_practices.py                  # seed all files
    python scripts/seed_best_practices.py --dry-run        # parse + chunk, no upload
    python scripts/seed_best_practices.py --force-reindex  # delete then re-upload
    python scripts/seed_best_practices.py --skip-verify    # skip post-upload checks

If the configured Pinecone index does not yet exist, the script creates it as
a serverless cosine index (1536 dims for text-embedding-3-small) in the
region specified by PINECONE_CLOUD/PINECONE_REGION (defaults: aws/us-east-1).

After upsert, the script verifies (a) the namespace vector count matches the
upload size, (b) a known vector ID can be fetched back, and (c) a smoke-test
query returns the expected source file as the top hit. Any failed check
exits non-zero so CI can catch a half-seeded index.

Required env (loaded from .env):
    OPENAI_API_KEY
    PINECONE_API_KEY
    OPENAI_PINECONE_INDEX_NAME

Optional env:
    EMBEDDING_MODEL          (default: text-embedding-3-small)
    EMBEDDING_DIMENSIONS     (default: 1536)
    PINECONE_CLOUD           (default: aws)
    PINECONE_REGION          (default: us-east-1)

Falls back to writing a local index at scripts/.local_corpus_index.json if
PINECONE_API_KEY is missing, so the demo can run fully offline. The
researcher agent reads that same file when USE_LOCAL_CORPUS=true.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
CORPUS_DIR = PROJECT_DIR / "tool_templates" / "best_practices"
LOCAL_INDEX_PATH = SCRIPT_DIR / ".local_corpus_index.json"

# ---------------------------------------------------------------------------
# Frontmatter + chunking
# ---------------------------------------------------------------------------

# Two metadata header styles are supported.
#
# Style A (YAML frontmatter):
#   ---
#   title: Latinx GOTV Field Playbook
#   source: Powerbuilder curated corpus
#   date: 2026-04-15
#   document_type: best_practices
#   tags: [latinx, gotv, field, spanish]
#   ---
#
# Style B (markdown header, used by the curated best-practices files):
#   # Title Of The Document
#
#   **Source:** Powerbuilder curated corpus, distilled from ...
#   **Date:** 2025-09-15
#   **Document type:** field playbook
#   **Topics:** latinx, gotv, canvassing, spanish
#
# Anything after the metadata block is the body. If neither header is
# present we derive a title from the filename and treat the full file as body.
FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.DOTALL)
MD_BOLD_FIELD_RE = re.compile(r"^\*\*([^*]+):\*\*\s*(.+?)\s*$")


def _parse_md_header(text: str, fallback_title: str) -> tuple[dict, str]:
    """
    Parse the markdown-style metadata header used by the curated corpus.

    Title comes from the first # heading; field rows look like
    `**Field:** value`. The body starts at the first non-metadata,
    non-blank line (typically the first ## section heading).
    """
    lines = text.splitlines()
    meta: dict = {"document_type": "best_practices"}
    title = fallback_title
    body_start = 0
    seen_meta = False

    for i, line in enumerate(lines):
        stripped = line.strip()

        if i == 0 and stripped.startswith("# ") and not stripped.startswith("## "):
            title = stripped[2:].strip()
            body_start = i + 1
            continue

        if not stripped:
            body_start = i + 1
            continue

        bold_match = MD_BOLD_FIELD_RE.match(stripped)
        if bold_match:
            key = bold_match.group(1).strip().lower().replace(" ", "_")
            val = bold_match.group(2).strip()
            # Topics: comma-separated tag list -> list of strings.
            if key == "topics":
                val = [t.strip() for t in val.split(",") if t.strip()]
                meta["tags"] = val
            else:
                meta[key] = val
            body_start = i + 1
            seen_meta = True
            continue

        # First non-metadata content line: stop scanning, keep as body start.
        break

    meta["title"] = title
    body = "\n".join(lines[body_start:]).strip()
    if not seen_meta and not body:
        # No metadata block and no remaining content: use full text as body.
        body = text
    return meta, body


def parse_frontmatter(text: str, fallback_title: str) -> tuple[dict, str]:
    """
    Parse a markdown file's metadata header (YAML frontmatter or markdown
    bold-field style) and return (metadata_dict, body).
    """
    match = FRONTMATTER_RE.match(text)
    if match:
        raw_meta, body = match.group(1), match.group(2)
        meta: dict = {}
        for line in raw_meta.splitlines():
            if ":" not in line:
                continue
            key, _, val = line.partition(":")
            key = key.strip()
            val = val.strip()
            if val.startswith("[") and val.endswith("]"):
                val = [v.strip().strip("'\"") for v in val[1:-1].split(",") if v.strip()]
            else:
                val = val.strip("'\"")
            meta[key] = val
        meta.setdefault("title", fallback_title)
        meta.setdefault("document_type", "best_practices")
        return meta, body

    # Fall back to markdown-bold-field header style.
    return _parse_md_header(text, fallback_title)


def chunk_markdown(body: str, max_chars: int = 1500) -> list[str]:
    """
    Split markdown body into chunks at paragraph boundaries.

    We keep chunks reasonably large (default 1500 chars) so each chunk carries
    enough context to be useful on its own. Paragraph boundaries are preferred
    over hard character limits, but if a single paragraph exceeds the limit,
    we fall back to splitting on sentences.
    """
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", body) if p.strip()]
    chunks: list[str] = []
    buf = ""

    for p in paragraphs:
        if len(p) > max_chars:
            # Long paragraph: flush whatever's buffered, then sentence-split.
            if buf:
                chunks.append(buf.strip())
                buf = ""
            sentences = re.split(r"(?<=[.!?])\s+", p)
            sub = ""
            for s in sentences:
                if len(sub) + len(s) + 1 > max_chars and sub:
                    chunks.append(sub.strip())
                    sub = s
                else:
                    sub = (sub + " " + s).strip()
            if sub:
                chunks.append(sub.strip())
            continue

        if len(buf) + len(p) + 2 > max_chars and buf:
            chunks.append(buf.strip())
            buf = p
        else:
            buf = (buf + "\n\n" + p).strip()

    if buf:
        chunks.append(buf.strip())

    return chunks


def vector_id(source_file: str, chunk_idx: int) -> str:
    """Deterministic ID so re-runs upsert (not duplicate)."""
    h = hashlib.sha1(f"{source_file}:{chunk_idx}".encode()).hexdigest()[:16]
    return f"bp-{h}"


# ---------------------------------------------------------------------------
# Document collection
# ---------------------------------------------------------------------------

def collect_documents() -> list[dict]:
    """
    Walk CORPUS_DIR and return one doc dict per chunk, ready to embed/upsert.
    """
    if not CORPUS_DIR.exists():
        raise FileNotFoundError(
            f"Corpus directory not found: {CORPUS_DIR}. "
            f"Did you run this from /powerbuilder?"
        )

    md_files = sorted(CORPUS_DIR.glob("*.md"))
    if not md_files:
        raise FileNotFoundError(f"No .md files found under {CORPUS_DIR}.")

    docs: list[dict] = []
    for md_path in md_files:
        text = md_path.read_text(encoding="utf-8")
        fallback_title = md_path.stem.replace("_", " ").title()
        meta, body = parse_frontmatter(text, fallback_title)
        chunks = chunk_markdown(body)

        for idx, chunk in enumerate(chunks):
            docs.append({
                "id": vector_id(md_path.name, idx),
                "text": chunk,
                "metadata": {
                    **meta,
                    "source_file": md_path.name,
                    "chunk_index": idx,
                    "total_chunks": len(chunks),
                    # langchain_pinecone reads "source" for citation display.
                    "source": meta.get("source", meta.get("title", md_path.name)),
                    # Map meta date into top-level for the researcher's recency sort.
                    "date": meta.get("date", ""),
                },
            })

    return docs


# ---------------------------------------------------------------------------
# Pinecone path
# ---------------------------------------------------------------------------

# langchain_pinecone uses sentinel "__default__" but the raw SDK uses "" for
# the default namespace. Keep this constant module-level so both upsert and
# verification paths agree.
DEFAULT_NS = ""
INDEX_READY_TIMEOUT_SECS = 120

# Smoke-test queries: each maps a representative natural-language query to the
# corpus file that should dominate the top results. If a top-3 match doesn't
# include the expected file, verification fails. Keep these tied to corpus
# files we expect to keep around.
SMOKE_TEST_QUERIES: list[tuple[str, str]] = [
    ("Spanish door knock Gwinnett", "01_latinx_gotv_field_playbook.md"),
    ("rural turf cut drive time", "10_rural_and_exurban_organizing.md"),
    ("Vietnamese Korean voter outreach", "08_aapi_multilanguage_outreach.md"),
    ("Gen Z text message script", "05_gen_z_outreach.md"),
]


def _ensure_index(pc, index_name: str, dimensions: int) -> None:
    """
    Create the Pinecone index if it does not exist and wait for it to be ready.

    Uses serverless cosine on aws/us-east-1 by default; override with
    PINECONE_CLOUD / PINECONE_REGION env vars.
    """
    existing = [idx.name for idx in pc.list_indexes()]
    if index_name in existing:
        return

    from pinecone import ServerlessSpec
    cloud = os.getenv("PINECONE_CLOUD", "aws")
    region = os.getenv("PINECONE_REGION", "us-east-1")
    print(f"Creating index '{index_name}' ({dimensions} dims, cosine, {cloud}/{region})...")
    pc.create_index(
        name=index_name,
        dimension=dimensions,
        metric="cosine",
        spec=ServerlessSpec(cloud=cloud, region=region),
    )

    deadline = time.time() + INDEX_READY_TIMEOUT_SECS
    while time.time() < deadline:
        info = pc.describe_index(index_name)
        if getattr(info.status, "ready", False):
            print(f"  Index '{index_name}' is ready.")
            return
        time.sleep(2)
    raise RuntimeError(
        f"Index '{index_name}' did not become ready within {INDEX_READY_TIMEOUT_SECS}s."
    )


def _verify_count(index, expected: int) -> int:
    """
    Poll describe_index_stats until the default namespace count reaches
    `expected` (or stops growing). Returns the observed count.
    Pinecone stats can lag a few seconds behind upsert.
    """
    deadline = time.time() + 30
    last = -1
    while time.time() < deadline:
        stats = index.describe_index_stats()
        ns = stats.namespaces or {}
        entry = ns.get(DEFAULT_NS) or ns.get("__default__")
        count = getattr(entry, "vector_count", 0) if entry else 0
        if count >= expected:
            return count
        if count == last:
            # Stats stopped moving; bail with what we have.
            time.sleep(2)
        last = count
        time.sleep(2)
    return last if last >= 0 else 0


def _verify_sample_fetch(index, sample_id: str) -> bool:
    """Confirm a known vector ID round-trips through fetch."""
    try:
        result = index.fetch(ids=[sample_id], namespace=DEFAULT_NS)
        vectors = getattr(result, "vectors", None) or {}
        return sample_id in vectors
    except Exception as exc:
        print(f"  sample fetch error: {exc}")
        return False


def _verify_smoke_queries(index, embeddings) -> list[tuple[str, str, bool, str]]:
    """
    Run each smoke-test query and check that the expected source file appears
    in the top 3 hits. Returns a list of (query, expected_file, passed, top_file).
    """
    results: list[tuple[str, str, bool, str]] = []
    for query, expected_file in SMOKE_TEST_QUERIES:
        try:
            vec = embeddings.embed_query(query)
            res = index.query(
                vector=vec, top_k=3, include_metadata=True, namespace=DEFAULT_NS,
            )
            top_files = [
                (m.metadata or {}).get("source_file", "?") for m in res.matches
            ]
            passed = expected_file in top_files
            top_file = top_files[0] if top_files else "?"
        except Exception as exc:
            passed = False
            top_file = f"error: {exc}"
        results.append((query, expected_file, passed, top_file))
    return results


def upsert_to_pinecone(
    docs: list[dict],
    force_reindex: bool,
    skip_verify: bool = False,
) -> bool:
    """
    Embed every chunk and upsert to OPENAI_PINECONE_INDEX_NAME / __default__.

    Returns True if upsert (and verification, if enabled) succeeded.
    """
    from langchain_openai import OpenAIEmbeddings
    from pinecone import Pinecone

    api_key = os.getenv("PINECONE_API_KEY")
    index_name = os.getenv("OPENAI_PINECONE_INDEX_NAME")
    if not (api_key and index_name):
        raise RuntimeError(
            "PINECONE_API_KEY and OPENAI_PINECONE_INDEX_NAME must be set."
        )

    embedding_model = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
    embedding_dims = int(os.getenv("EMBEDDING_DIMENSIONS", "1536"))

    pc = Pinecone(api_key=api_key)
    _ensure_index(pc, index_name, embedding_dims)
    index = pc.Index(index_name)
    embeddings = OpenAIEmbeddings(model=embedding_model)

    if force_reindex:
        ids_to_delete = [d["id"] for d in docs]
        # Pinecone enforces a 1000-id limit per delete call.
        for i in range(0, len(ids_to_delete), 1000):
            batch = ids_to_delete[i:i + 1000]
            try:
                index.delete(ids=batch, namespace=DEFAULT_NS)
            except Exception as exc:
                # If the IDs don't exist yet (first run), Pinecone may 404. Ignore.
                print(f"  delete batch skipped: {exc}")

    print(f"Embedding {len(docs)} chunks with {embedding_model}...")
    texts = [d["text"] for d in docs]
    vectors = embeddings.embed_documents(texts)

    print(f"Upserting to index '{index_name}', namespace '__default__'...")
    payload = [
        {"id": d["id"], "values": vec, "metadata": {**d["metadata"], "text": d["text"]}}
        for d, vec in zip(docs, vectors)
    ]
    # Pinecone allows up to 100 vectors per upsert call.
    for i in range(0, len(payload), 100):
        index.upsert(vectors=payload[i:i + 100], namespace=DEFAULT_NS)

    print(f"Done. Upserted {len(payload)} vectors.")

    if skip_verify:
        print("Skip-verify flag set: skipping post-upload checks.")
        return True

    return _run_post_upload_verification(index, embeddings, docs)


def _run_post_upload_verification(index, embeddings, docs: list[dict]) -> bool:
    """
    Three checks: count match, sample fetch, smoke-test queries.
    Prints a summary and returns True only if every check passes.
    """
    print("\nVerifying upload...")
    expected = len(docs)
    count = _verify_count(index, expected)
    count_ok = count >= expected
    print(f"  [{'OK' if count_ok else 'FAIL'}] vector count: {count} / {expected}")

    sample_id = docs[0]["id"] if docs else ""
    fetch_ok = bool(sample_id) and _verify_sample_fetch(index, sample_id)
    print(f"  [{'OK' if fetch_ok else 'FAIL'}] sample fetch: id={sample_id}")

    smoke_results = _verify_smoke_queries(index, embeddings)
    smoke_ok = all(passed for _, _, passed, _ in smoke_results)
    print("  Smoke-test queries:")
    for query, expected_file, passed, top_file in smoke_results:
        marker = "OK" if passed else "FAIL"
        print(f"    [{marker}] {query!r} -> top={top_file} (expected {expected_file})")

    all_ok = count_ok and fetch_ok and smoke_ok
    print(f"\nVerification: {'PASS' if all_ok else 'FAIL'}")
    return all_ok


# ---------------------------------------------------------------------------
# Local fallback path
# ---------------------------------------------------------------------------

def write_local_index(docs: list[dict]) -> None:
    """
    Persist chunks to a local JSON file the researcher can read when Pinecone
    is unavailable or USE_LOCAL_CORPUS=true. No embeddings, just the text and
    metadata; the researcher does keyword scoring against this index.
    """
    payload = {
        "version": 1,
        "chunks": [
            {
                "id": d["id"],
                "text": d["text"],
                "metadata": d["metadata"],
            }
            for d in docs
        ],
    }
    LOCAL_INDEX_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote local fallback index: {LOCAL_INDEX_PATH} ({len(docs)} chunks)")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="Seed best-practices corpus.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Parse and chunk but do not embed or upload.")
    parser.add_argument("--force-reindex", action="store_true",
                        help="Delete existing vectors with these IDs before upsert.")
    parser.add_argument("--local-only", action="store_true",
                        help="Skip Pinecone, write only the local fallback index.")
    parser.add_argument("--skip-verify", action="store_true",
                        help="Skip post-upload count check, sample fetch, and smoke-test queries.")
    args = parser.parse_args()

    docs = collect_documents()
    print(f"Collected {len(docs)} chunks from {CORPUS_DIR}.")
    by_file: dict[str, int] = {}
    for d in docs:
        f = d["metadata"]["source_file"]
        by_file[f] = by_file.get(f, 0) + 1
    for f, n in sorted(by_file.items()):
        print(f"  {f}: {n} chunks")

    # Always write the local fallback so the researcher has an offline option
    # the moment we run the seeder for the first time.
    write_local_index(docs)

    if args.dry_run:
        print("Dry run complete. No upload.")
        return 0

    if args.local_only:
        print("local-only flag set: skipping Pinecone upload.")
        return 0

    if not os.getenv("PINECONE_API_KEY"):
        print("PINECONE_API_KEY not set: falling back to local-only mode.")
        return 0

    try:
        verified = upsert_to_pinecone(
            docs,
            force_reindex=args.force_reindex,
            skip_verify=args.skip_verify,
        )
    except Exception as exc:
        print(f"Pinecone upload failed: {exc}")
        print("Local fallback index is still available.")
        return 1

    if not verified:
        print("Verification failed: index may be incomplete or stale.")
        return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
