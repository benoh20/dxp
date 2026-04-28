"""
Validate the researcher's local corpus fallback path.

This test does not import the real researcher module (which pulls in Django,
Pinecone, and LangChain), it imports the helper functions directly so we can
exercise tokenization, scoring, and ranking without network or DB access.

Run from /powerbuilder:
    python scripts/_test_local_corpus_fallback.py
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# Path bootstrap: insert powerbuilder/ on sys.path so we can import the
# researcher helpers without triggering Django setup.
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(PROJECT_DIR))

# Force the local-corpus path before importing.
os.environ["USE_LOCAL_CORPUS"] = "true"
os.environ.pop("PINECONE_API_KEY", None)


def main() -> int:
    failures: list[str] = []

    # 1. Local index exists and has chunks across all 8 source files.
    index_path = SCRIPT_DIR / ".local_corpus_index.json"
    if not index_path.exists():
        print(f"FAIL: local index missing at {index_path}")
        print("Run `python scripts/seed_best_practices.py --local-only` first.")
        return 1
    payload = json.loads(index_path.read_text())
    chunks = payload["chunks"]
    if len(chunks) < 8:
        failures.append(f"expected >=8 chunks, got {len(chunks)}")
    sources = {c["metadata"]["source_file"] for c in chunks}
    if len(sources) != 8:
        failures.append(f"expected 8 distinct source files, got {len(sources)}: {sources}")

    # 2. Frontmatter parsing extracted real titles, not filename fallbacks.
    titles = {c["metadata"].get("title", "") for c in chunks}
    must_contain = ["Latinx GOTV", "Spanish", "Gwinnett"]
    for needle in must_contain:
        if not any(needle in t for t in titles):
            failures.append(f"no title contains '{needle}'; titles={sorted(titles)}")

    # 3. Tags were extracted as lists, not strings.
    sample_tags = [c["metadata"].get("tags") for c in chunks if c["metadata"].get("tags")]
    if not sample_tags:
        failures.append("no chunk has tags metadata")
    elif not all(isinstance(t, list) for t in sample_tags):
        failures.append(f"tags should be lists, got {[type(t).__name__ for t in sample_tags[:3]]}")

    # 4. Scoring: a Spanish/Latinx GOTV query should rank file 01 first.
    from chat.agents.researcher import _local_corpus_search, _load_local_corpus

    # Reset the cache so our env-var override takes effect.
    import chat.agents.researcher as researcher_mod
    researcher_mod._local_corpus_cache = None

    loaded = _load_local_corpus()
    if len(loaded) != len(chunks):
        failures.append(f"loader returned {len(loaded)} chunks, expected {len(chunks)}")

    results = _local_corpus_search(
        "Spanish door knock script for Latinx GOTV in Gwinnett",
        k=3,
    )
    if not results:
        failures.append("local search returned no results for Spanish/Latinx/Gwinnett query")
    else:
        top_source = results[0].metadata.get("source_file", "")
        if "latinx" not in top_source.lower() and "spanish" not in top_source.lower():
            failures.append(
                f"top result for Spanish/Latinx query was {top_source}, "
                f"expected file 01 or 02"
            )

    # 5. Scoring: a Gen Z query should pull file 05 into the top results.
    results_genz = _local_corpus_search("How do we reach Gen Z young voters?", k=5)
    top_files_genz = [r.metadata.get("source_file", "") for r in results_genz]
    if not any("gen_z" in f.lower() for f in top_files_genz):
        failures.append(f"Gen Z query did not surface file 05, got {top_files_genz}")

    # 5b. Paid media query should surface file 07.
    results_paid = _local_corpus_search(
        "What is the CPM for YouTube and Meta civic ads, and what does $50K buy me?",
        k=5,
    )
    top_files_paid = [r.metadata.get("source_file", "") for r in results_paid]
    if not any("paid_media" in f.lower() for f in top_files_paid):
        failures.append(f"Paid media query did not surface file 07, got {top_files_paid}")

    # 5c. AAPI multi-language query should surface file 08.
    results_aapi = _local_corpus_search(
        "How should we do Korean and Vietnamese language outreach for AAPI voters?",
        k=5,
    )
    top_files_aapi = [r.metadata.get("source_file", "") for r in results_aapi]
    if not any("aapi" in f.lower() for f in top_files_aapi):
        failures.append(f"AAPI multi-language query did not surface file 08, got {top_files_aapi}")

    # 6. Score with empty query returns nothing.
    empty_results = _local_corpus_search("", k=5)
    if empty_results:
        failures.append(f"empty query should return [], got {len(empty_results)} results")

    # 7. Output shape compatibility: results expose page_content + metadata
    #    (the researcher's _format_results helper depends on that shape).
    if results:
        r = results[0]
        if not hasattr(r, "page_content") or not hasattr(r, "metadata"):
            failures.append("local search result missing page_content/metadata attributes")

    # Report.
    print(f"Local corpus fallback test: {len(chunks)} chunks across {len(sources)} files.")
    if failures:
        print(f"FAIL: {len(failures)} assertion(s) failed:")
        for f in failures:
            print(f"  - {f}")
        return 1

    print("PASS: all 9 assertion groups OK.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
