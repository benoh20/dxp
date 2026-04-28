"""
Offline tests for the post-upload verification logic in seed_best_practices.py.

We do not hit real Pinecone or OpenAI here. Instead, we build a minimal fake
Pinecone index plus a fake embeddings client and exercise:

  1. _verify_count: count match, count short, count growth-then-stall
  2. _verify_sample_fetch: id present vs id missing
  3. _verify_smoke_queries: top hit matches expected file vs does not
  4. _run_post_upload_verification: end-to-end PASS and FAIL summaries

Run: ./venv/bin/python scripts/_test_seed_verification.py
"""
from __future__ import annotations

import sys
import types
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import seed_best_practices as seed  # noqa: E402


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------

@dataclass
class FakeNamespaceStats:
    vector_count: int


@dataclass
class FakeStats:
    namespaces: dict[str, FakeNamespaceStats]


@dataclass
class FakeMatch:
    id: str
    score: float
    metadata: dict[str, Any]


@dataclass
class FakeQueryResult:
    matches: list[FakeMatch]


@dataclass
class FakeFetchResult:
    vectors: dict[str, Any]


class FakeIndex:
    """
    Minimal fake of pinecone.Index that supports describe_index_stats, fetch,
    and query. Behavior is driven by attributes the test sets up front.
    """

    def __init__(
        self,
        count_sequence: list[int],
        fetch_ids: set[str],
        query_responder,
    ):
        # describe_index_stats returns the next count from count_sequence each
        # call (clamped to last value). Lets us simulate stats lag.
        self._count_sequence = list(count_sequence)
        self._fetch_ids = fetch_ids
        self._query_responder = query_responder

    def describe_index_stats(self) -> FakeStats:
        if len(self._count_sequence) > 1:
            count = self._count_sequence.pop(0)
        else:
            count = self._count_sequence[0]
        return FakeStats(namespaces={"": FakeNamespaceStats(vector_count=count)})

    def fetch(self, ids, namespace=""):
        present = {i: object() for i in ids if i in self._fetch_ids}
        return FakeFetchResult(vectors=present)

    def query(self, vector, top_k, include_metadata, namespace=""):
        return self._query_responder(vector, top_k)


class FakeEmbeddings:
    """
    Encodes a stable hash of the query text into the first vector slot so
    the responder can route distinct queries to distinct results.
    """

    @staticmethod
    def _key(text: str) -> int:
        # Deterministic, collision-resistant within our small test set.
        import hashlib
        return int(hashlib.sha1(text.encode()).hexdigest()[:8], 16)

    def embed_query(self, text: str) -> list[float]:
        return [float(self._key(text))] + [0.0] * 1535


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_responder(top_file_by_query_text: dict[str, str]):
    """
    Build a query responder where each known smoke-test query returns three
    matches; the first match's source_file is the value from
    top_file_by_query_text. Anything else returns no matches.

    We route by vector[0] which encodes a hash of the query text.
    """
    by_key = {FakeEmbeddings._key(q): src for q, src in top_file_by_query_text.items()}

    def responder(vector, top_k):
        key = int(vector[0])
        src = by_key.get(key)
        if not src:
            return FakeQueryResult(matches=[])
        # Build top_k matches; first is the targeted one.
        matches = [
            FakeMatch(id=f"m{i}", score=0.9 - 0.1 * i, metadata={"source_file": src if i == 0 else "OTHER.md"})
            for i in range(top_k)
        ]
        return FakeQueryResult(matches=matches)

    return responder


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_verify_count_reaches_expected():
    # Stats lag two calls behind, then catches up.
    index = FakeIndex(count_sequence=[60, 65, 68], fetch_ids=set(), query_responder=lambda *a, **k: None)
    count = seed._verify_count(index, expected=68)
    assert count >= 68, f"expected >=68, got {count}"


def test_verify_count_short():
    # Stats stall at 60; verifier should give up and return what it saw.
    index = FakeIndex(count_sequence=[60], fetch_ids=set(), query_responder=lambda *a, **k: None)
    count = seed._verify_count(index, expected=68)
    assert count < 68, f"expected stall under 68, got {count}"


def test_verify_sample_fetch_hit_and_miss():
    index = FakeIndex(count_sequence=[68], fetch_ids={"bp-abc"}, query_responder=lambda *a, **k: None)
    assert seed._verify_sample_fetch(index, "bp-abc") is True
    assert seed._verify_sample_fetch(index, "bp-missing") is False


def test_verify_smoke_queries_all_pass():
    expected_map = {q: src for q, src in seed.SMOKE_TEST_QUERIES}
    responder = _make_responder(expected_map)
    index = FakeIndex(count_sequence=[68], fetch_ids=set(), query_responder=responder)
    results = seed._verify_smoke_queries(index, FakeEmbeddings())
    assert len(results) == len(seed.SMOKE_TEST_QUERIES)
    assert all(passed for _, _, passed, _ in results), f"expected all pass, got {results}"


def test_verify_smoke_queries_one_fails():
    # Sabotage one query: route it to the wrong file.
    bad_map = {q: ("WRONG.md" if i == 0 else src) for i, (q, src) in enumerate(seed.SMOKE_TEST_QUERIES)}
    responder = _make_responder(bad_map)
    index = FakeIndex(count_sequence=[68], fetch_ids=set(), query_responder=responder)
    results = seed._verify_smoke_queries(index, FakeEmbeddings())
    passed_flags = [passed for _, _, passed, _ in results]
    assert passed_flags[0] is False, "first query should fail"
    assert all(passed_flags[1:]), "remaining queries should pass"


def test_run_post_upload_verification_pass():
    expected_map = {q: src for q, src in seed.SMOKE_TEST_QUERIES}
    responder = _make_responder(expected_map)
    docs = [{"id": "bp-first", "text": "x", "metadata": {}}] * 68
    docs[0] = {"id": "bp-first", "text": "x", "metadata": {}}  # ensure first id exists
    index = FakeIndex(count_sequence=[68], fetch_ids={"bp-first"}, query_responder=responder)
    ok = seed._run_post_upload_verification(index, FakeEmbeddings(), docs)
    assert ok is True


def test_run_post_upload_verification_fail_on_count():
    expected_map = {q: src for q, src in seed.SMOKE_TEST_QUERIES}
    responder = _make_responder(expected_map)
    docs = [{"id": "bp-first", "text": "x", "metadata": {}} for _ in range(68)]
    index = FakeIndex(count_sequence=[40], fetch_ids={"bp-first"}, query_responder=responder)
    ok = seed._run_post_upload_verification(index, FakeEmbeddings(), docs)
    assert ok is False


def test_run_post_upload_verification_fail_on_fetch():
    expected_map = {q: src for q, src in seed.SMOKE_TEST_QUERIES}
    responder = _make_responder(expected_map)
    docs = [{"id": "bp-first", "text": "x", "metadata": {}} for _ in range(68)]
    index = FakeIndex(count_sequence=[68], fetch_ids=set(), query_responder=responder)  # id missing
    ok = seed._run_post_upload_verification(index, FakeEmbeddings(), docs)
    assert ok is False


def test_smoke_test_queries_cover_each_known_file():
    # Sanity: every smoke query maps to a real corpus file we ship.
    corpus_dir = Path(__file__).resolve().parent.parent / "tool_templates" / "best_practices"
    existing = {p.name for p in corpus_dir.glob("*.md")}
    for query, expected_file in seed.SMOKE_TEST_QUERIES:
        assert expected_file in existing, f"smoke query {query!r} references missing file {expected_file}"


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def main() -> int:
    tests = [
        test_verify_count_reaches_expected,
        test_verify_count_short,
        test_verify_sample_fetch_hit_and_miss,
        test_verify_smoke_queries_all_pass,
        test_verify_smoke_queries_one_fails,
        test_run_post_upload_verification_pass,
        test_run_post_upload_verification_fail_on_count,
        test_run_post_upload_verification_fail_on_fetch,
        test_smoke_test_queries_cover_each_known_file,
    ]
    failures = 0
    for t in tests:
        try:
            t()
            print(f"  OK   {t.__name__}")
        except AssertionError as exc:
            failures += 1
            print(f"  FAIL {t.__name__}: {exc}")
        except Exception as exc:
            failures += 1
            print(f"  ERR  {t.__name__}: {exc}")
    print(f"\n{len(tests) - failures}/{len(tests)} passed.")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
