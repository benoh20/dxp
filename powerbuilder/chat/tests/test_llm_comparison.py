"""
test_llm_comparison.py

Side-by-side LLM provider comparison test.

For each configured provider:
  1. Retrieval  — searches the provider's Pinecone index using its native
                  embedding model (falls back to OpenAI for providers without
                  native embeddings: anthropic, groq).
  2. Completion — generates an answer using that provider's completion model.
  3. Timing     — records wall-clock seconds for retrieval and completion separately.

Providers are tested concurrently (one thread per provider).
Results are saved to exports/llm_comparison_report.md.

Run from the project root:
    python chat/tests/test_llm_comparison.py
    python -m pytest chat/tests/test_llm_comparison.py -v -s
"""

import os
import sys
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

# load_dotenv MUST be first — before any import that touches API keys
from dotenv import load_dotenv
load_dotenv()

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

import pytest

from chat.utils.llm_config import (
    PINECONE_INDEX_NAMES,
    EmbeddingConfig,
    get_completion_client,
    get_configured_providers,
    get_embedding_client,
)

# ---------------------------------------------------------------------------
# Test queries — same as test_full_pipeline.py
# ---------------------------------------------------------------------------

QUERIES = [
    {
        "id":    "young_voters",
        "label": "Q1: Young voter targeting + messaging",
        "text":  (
            "I want to reach young voters in Virginia's 7th Congressional District. "
            "What precincts should I target and what message should I deliver?"
        ),
    },
    {
        "id":    "canvassing_cost",
        "label": "Q2: Canvassing cost estimate",
        "text":  (
            "How much would it cost to run a canvassing program "
            "in Virginia's 7th Congressional District in 2026?"
        ),
    },
    {
        "id":    "win_number",
        "label": "Q3: Win number",
        "text":  "What is the win number for Virginia's 7th Congressional District in 2026?",
    },
]

# Pinecone top-K for comparison retrieval
RETRIEVAL_K = 5

# Exports directory — mirrors export_node
EXPORTS_DIR = os.getenv(
    "EXPORTS_DIR",
    os.path.abspath(os.path.join(os.path.dirname(__file__), "../../exports")),
)

# ---------------------------------------------------------------------------
# Per-provider result container
# ---------------------------------------------------------------------------

_lock = threading.Lock()


def _index_exists(index_name: str) -> bool:
    """Return True if the named Pinecone index exists."""
    try:
        from pinecone import Pinecone
        pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY", ""))
        return any(idx.name == index_name for idx in pc.list_indexes())
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Single-provider, single-query run
# ---------------------------------------------------------------------------

def _run_one(provider_info: dict, query: dict) -> dict:
    """
    Execute one retrieval + completion for *provider_info* against *query*.

    Returns a result dict:
        provider, query_id, query_label,
        retrieval_sources, retrieval_time_s,
        completion_answer, completion_time_s,
        error (str or None)
    """
    provider   = provider_info["provider"]
    query_id   = query["id"]
    query_text = query["text"]

    result = {
        "provider":          provider,
        "model":             provider_info["model"],
        "embedding_model":   provider_info.get("embedding_model") or "openai (fallback)",
        "index_name":        provider_info["index_name"],
        "query_id":          query_id,
        "query_label":       query["label"],
        "retrieval_sources": [],
        "retrieval_snippets": [],
        "retrieval_time_s":  None,
        "completion_answer": "",
        "completion_time_s": None,
        "error":             None,
    }

    # ------------------------------------------------------------------
    # 1. Retrieval
    # ------------------------------------------------------------------
    try:
        emb_cfg    = get_embedding_client(provider=provider)
        index_name = emb_cfg.index_name

        if not _index_exists(index_name):
            result["error"] = (
                f"Index '{index_name}' does not exist. "
                "Run comparison_ingestor.py first."
            )
            return result

        from langchain_pinecone import PineconeVectorStore
        t0    = time.perf_counter()
        store = PineconeVectorStore(
            index_name=index_name,
            embedding=emb_cfg.client,
            namespace="__default__",
            text_key="text",
        )
        docs  = store.similarity_search(query_text, k=RETRIEVAL_K)
        result["retrieval_time_s"] = round(time.perf_counter() - t0, 2)

        result["retrieval_sources"] = [
            d.metadata.get("source", "unknown") for d in docs
        ]
        result["retrieval_snippets"] = [
            d.page_content[:200].replace("\n", " ") for d in docs
        ]
        context = "\n\n".join(
            f"[{d.metadata.get('source','?')} | {d.metadata.get('date','?')}]\n"
            f"{d.page_content[:800]}"
            for d in docs
        )
    except Exception as e:
        result["error"] = f"Retrieval failed: {e}"
        return result

    # ------------------------------------------------------------------
    # 2. Completion
    # ------------------------------------------------------------------
    try:
        llm    = get_completion_client(temperature=0.3, provider=provider)
        prompt = (
            "You are a political strategist. Answer the following question using "
            "only the research context provided. Be concise (3–5 sentences).\n\n"
            f"CONTEXT:\n{context}\n\n"
            f"QUESTION: {query_text}"
        )
        t0     = time.perf_counter()
        answer = llm.invoke(prompt).content.strip()
        result["completion_time_s"] = round(time.perf_counter() - t0, 2)
        result["completion_answer"] = answer
    except Exception as e:
        result["error"] = f"Completion failed: {e}"

    return result


# ---------------------------------------------------------------------------
# Run all providers × all queries concurrently
# ---------------------------------------------------------------------------

def run_comparison(providers: list[dict] | None = None) -> list[dict]:
    """
    Run all configured providers against all QUERIES concurrently.

    Args:
        providers: Override the list of providers (default: get_configured_providers()).

    Returns:
        Flat list of result dicts, one per (provider × query) combination.
    """
    if providers is None:
        providers = get_configured_providers()

    if not providers:
        print("No providers configured. Check your API keys.")
        return []

    tasks = [(p, q) for p in providers for q in QUERIES]
    results: list[dict] = []

    print(f"\nRunning {len(providers)} providers x {len(QUERIES)} queries "
          f"= {len(tasks)} tasks (concurrent)\n")

    with ThreadPoolExecutor(max_workers=min(len(tasks), 8)) as pool:
        futures = {pool.submit(_run_one, p, q): (p["provider"], q["id"]) for p, q in tasks}
        for future in as_completed(futures):
            provider_name, query_id = futures[future]
            try:
                res = future.result()
            except Exception as e:
                res = {
                    "provider":    provider_name,
                    "query_id":    query_id,
                    "error":       str(e),
                    "completion_answer": "",
                    "retrieval_sources": [],
                }
            with _lock:
                results.append(res)
                status = res.get("error") or "ok"
                print(f"  [{provider_name:12}] {query_id:20} -> {status}")

    return results


# ---------------------------------------------------------------------------
# Report writer
# ---------------------------------------------------------------------------

def _fmt_time(val) -> str:
    return f"{val:.2f}s" if val is not None else "N/A"


def write_report(results: list[dict], path: str) -> None:
    """Write a side-by-side Markdown comparison report to *path*."""
    os.makedirs(os.path.dirname(path), exist_ok=True)

    # Group results: provider → query_id → result
    by_provider: dict[str, dict] = {}
    for r in results:
        by_provider.setdefault(r["provider"], {})[r["query_id"]] = r

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    lines = [
        "# Powerbuilder LLM Provider Comparison Report",
        "",
        f"**Generated:** {now}  ",
        f"**Providers tested:** {', '.join(sorted(by_provider.keys()))}  ",
        f"**Queries:** {len(QUERIES)}  ",
        "",
        "---",
        "",
    ]

    # One H2 section per provider
    for provider in sorted(by_provider.keys()):
        queries = by_provider[provider]
        # Pull metadata from first result
        first  = next(iter(queries.values()))
        model  = first.get("model", "unknown")
        emb    = first.get("embedding_model", "unknown")
        idx    = first.get("index_name", "unknown")

        lines += [
            f"## {provider.title()}",
            "",
            f"| Field | Value |",
            f"|-------|-------|",
            f"| Completion model | `{model}` |",
            f"| Embedding model  | `{emb}` |",
            f"| Pinecone index   | `{idx}` |",
            "",
        ]

        for q in QUERIES:
            qid = q["id"]
            r   = queries.get(qid, {})
            err = r.get("error")

            lines += [
                f"### {q['label']}",
                "",
                f"> *{q['text']}*",
                "",
            ]

            if err:
                lines += [f"**Error:** `{err}`", ""]
                continue

            lines += [
                f"**Retrieval** ({_fmt_time(r.get('retrieval_time_s'))})  ",
                f"Sources: {', '.join(r.get('retrieval_sources', [])) or 'none'}",
                "",
            ]
            for i, snippet in enumerate(r.get("retrieval_snippets", []), 1):
                lines.append(f"{i}. _{snippet}_")
            lines.append("")

            lines += [
                f"**Completion** ({_fmt_time(r.get('completion_time_s'))})  ",
                "",
                r.get("completion_answer", "*(no answer)*"),
                "",
            ]

        lines += ["---", ""]

    # ChangeAgent placeholder section
    lines += [
        "## ChangeAgent",
        "",
        "ChangeAgent: pending API integration",
        "",
        "_This section will be populated automatically once ChangeAgent is registered "
        "via `register_custom_provider()` in llm_config.py._",
        "",
        "---",
        "",
    ]

    # Timing summary table
    lines += [
        "## Timing Summary",
        "",
        "| Provider | Query | Retrieval | Completion | Total |",
        "|----------|-------|-----------|------------|-------|",
    ]
    for r in sorted(results, key=lambda x: (x.get("provider",""), x.get("query_id",""))):
        if r.get("error"):
            continue
        ret  = r.get("retrieval_time_s")
        comp = r.get("completion_time_s")
        tot  = (ret or 0) + (comp or 0)
        lines.append(
            f"| {r['provider']:12} | {r['query_id']:20} | "
            f"{_fmt_time(ret):8} | {_fmt_time(comp):10} | {tot:.2f}s |"
        )
    lines.append("")

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"\nReport saved to: {path}")


# ---------------------------------------------------------------------------
# pytest integration
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def comparison_results():
    """Run the full comparison once per test module and cache results."""
    return run_comparison()


class TestSection0PreFlight:

    def test_openai_key_present(self):
        assert os.getenv("OPENAI_API_KEY"), "OPENAI_API_KEY is required (used as embedding fallback)"

    def test_pinecone_key_present(self):
        assert os.getenv("PINECONE_API_KEY"), "PINECONE_API_KEY is required"

    def test_at_least_one_provider_configured(self):
        providers = get_configured_providers()
        assert providers, "No LLM providers configured — set at least one API key"
        print(f"\nConfigured providers: {[p['provider'] for p in providers]}")

    def test_openai_index_exists(self):
        src = os.getenv("OPENAI_PINECONE_INDEX_NAME", "openai-research-index")
        assert _index_exists(src), (
            f"Source index '{src}' not found. Run bulk_upload.py first."
        )


class TestSection1Results:

    def test_all_providers_returned_answers(self, comparison_results):
        """Every configured provider should produce a non-empty answer for Q3 (win number)."""
        providers = get_configured_providers()
        for p in providers:
            name = p["provider"]
            r = next(
                (x for x in comparison_results
                 if x["provider"] == name and x["query_id"] == "win_number"),
                None,
            )
            assert r is not None, f"No result for provider '{name}'"
            if r.get("error") and "does not exist" in r["error"]:
                pytest.skip(f"Index for {name} not yet created — run comparison_ingestor.py")
            assert not r.get("error"), f"{name} error: {r['error']}"
            assert len(r.get("completion_answer", "")) > 20, \
                f"{name} returned an empty answer"

    def test_retrieval_times_recorded(self, comparison_results):
        """Retrieval time must be recorded for every successful result."""
        for r in comparison_results:
            if r.get("error"):
                continue
            assert r.get("retrieval_time_s") is not None, \
                f"Missing retrieval_time_s for {r['provider']} / {r['query_id']}"

    def test_report_written(self, comparison_results):
        """Report file must be created and non-empty."""
        path = os.path.join(EXPORTS_DIR, "llm_comparison_report.md")
        write_report(comparison_results, path)
        assert os.path.exists(path)
        assert os.path.getsize(path) > 500
        print(f"\nReport: {path}")

    def test_report_contains_change_agent_placeholder(self, comparison_results):
        """The ChangeAgent placeholder must appear in the report."""
        path = os.path.join(EXPORTS_DIR, "llm_comparison_report.md")
        if not os.path.exists(path):
            write_report(comparison_results, path)
        content = open(path, encoding="utf-8").read()
        assert "ChangeAgent: pending API integration" in content


# ---------------------------------------------------------------------------
# Standalone runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    providers = get_configured_providers()
    print(f"Configured providers ({len(providers)}):")
    for p in providers:
        emb = "native embed" if p["embedding_available"] else "OpenAI embed fallback"
        print(f"  {p['provider']:12} completion={p['model']}  [{emb}]")

    results = run_comparison(providers)

    path = os.path.join(EXPORTS_DIR, "llm_comparison_report.md")
    write_report(results, path)

    # Print brief summary
    print("\n=== ANSWER LENGTHS ===")
    for r in sorted(results, key=lambda x: (x.get("provider",""), x.get("query_id",""))):
        if r.get("error"):
            print(f"  {r['provider']:12} {r['query_id']:20}  ERROR: {r['error'][:60]}")
        else:
            print(
                f"  {r['provider']:12} {r['query_id']:20}  "
                f"ret={_fmt_time(r.get('retrieval_time_s')):6}  "
                f"cmp={_fmt_time(r.get('completion_time_s')):6}  "
                f"ans={len(r.get('completion_answer',''))} chars"
            )
