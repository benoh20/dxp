# [APP_NAME]

**An AI-orchestrated civic engagement platform for nonpartisan voter outreach, education, and field operations.**

[APP_NAME] is a Django + LangGraph application that coordinates a team of specialist AI agents (researcher, win-number, precincts, messaging, opposition research, voter-file analyst, and more) to generate full civic engagement plans, segment-targeted messaging, and budget estimates from a single natural-language request. The current public deployment lives at [powerbuilder.app](https://powerbuilder.app).

Built by [Benjamin Oh](https://github.com/benoh20) and [Rosario Palacios](https://github.com/Mdr-palacios) as part of the **DxP Fellowship**.

> **Note on naming:** `[APP_NAME]` is a placeholder. The fellowship is DxP; the app does not yet have a final name. Find-and-replace `[APP_NAME]` once a name is chosen.

---

## What it does

An organizer or program manager types a request in plain English (or Spanish):

> "Build me a Gwinnett County GOTV plan targeting Latinx voters 18-35 with a Spanish door-knock script and a CSV export."

[APP_NAME] routes the request through a LangGraph orchestrator that decides which specialist agents to call, in what order. Each agent writes its findings back to a shared whiteboard (`AgentState`). A synthesizer agent assembles the final deliverable (Markdown, DOCX, or CSV), grounded in research drawn from a curated Pinecone-backed corpus and live data sources (US Census, FEC, ChangeAgent).

## Why it exists

Most civic technology is sold to large institutions and staffed by analysts. The independent organizer, the community-based field program, and the local nonpartisan voter education effort rarely have access to the same caliber of strategic planning or research synthesis. [APP_NAME] exists to close that gap with software that does the work of a junior strategist, a research analyst, and a field director, without replacing any of them.

---

## Architecture

```
┌────────────────────────────────────────────────────────────────┐
│                     Django (HTMX views)                        │
│                       chat/views.py                            │
└────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌────────────────────────────────────────────────────────────────┐
│                   LangGraph Orchestrator                       │
│                  chat/agents/manager.py                        │
│                                                                │
│   intent_router → [specialist] → intent_router → … → synth    │
└────────────────────────────────────────────────────────────────┘
                              │
        ┌─────────────┬───────┴────────┬─────────────┐
        ▼             ▼                ▼             ▼
   Researcher   Win Number       Precincts     Messaging
   (Pinecone)   (Census API)     (Census +     (LLM + tool_
                                  geo files)    templates/)

   Election     Opposition       Voter File    Cost
   Results      Research         (CSV/XLSX)    Calculator
   (FEC API)    (Pinecone)
                              │
                              ▼
                       Synthesizer (export.py)
                              │
                              ▼
                  Markdown / DOCX / XLSX / CSV
```

### Key components

- **`chat/agents/manager.py`**: LangGraph state machine. Detects intent, demographic targeting, and language from the query. Routes to one specialist at a time and loops back until the work is done.
- **`chat/agents/state.py`**: the shared whiteboard (`AgentState` TypedDict). Every agent reads and writes through this contract.
- **`chat/agents/researcher.py`**: dual-namespace Pinecone search across a general corpus (`__default__`) and per-org private namespaces. Returns memos sorted by recency.
- **`chat/agents/messaging.py`**: generates five messaging formats (canvass, phone, text, mail, digital) grounded exclusively in researcher findings. Honors `language_intent` for Spanish, Mandarin, Vietnamese, and Korean output.
- **`chat/agents/voterfile_agent.py`**: vendor-aware voter file processor. Auto-detects TargetSmart / Catalist / L2 / VAN exports, standardizes column names, and segments by age cohort, language, geography, and turnout propensity.
- **`chat/agents/precincts.py`** + **`win_number.py`** + **`election_results.py`**: geographic and electoral analysis. Pull live US Census CVAP and FEC data.
- **`tool_templates/`**: editable Markdown templates for each output format (canvass scripts, phone scripts, etc.) plus `costs.json` for cost-per-contact rates. Drop a new `.md` in here to change copy structure without touching code.

### Data isolation

Every Pinecone read and write is scoped to an `org_namespace` derived from the authenticated user's email domain. The `__default__` namespace holds the curated public corpus (American Bridge research books, Analyst Institute briefs, the [APP_NAME] best-practices set). Per-org uploads never leave their namespace.

Voter file data is processed in-memory and discarded at the end of the request. Nothing is persisted.

---

## Quickstart

### Prerequisites

- Python 3.12+
- An OpenAI API key (required: used for embeddings even when other LLMs are the chat provider)
- A Pinecone account + API key (optional for local dev: the app falls back to a local best-practices corpus when Pinecone is unreachable)
- A US Census API key (free, [signup here](https://api.census.gov/data/key_signup.html))
- A LlamaParse key (only needed for ingesting new PDFs; not needed to run)

### Setup

```bash
git clone https://github.com/benoh20/dxp.git
cd dxp/powerbuilder

python3 -m venv venv
source venv/bin/activate

pip install -r requirements.txt

cp .env.example .env   # then fill in your keys
python manage.py migrate
python manage.py runserver
```

Open http://localhost:8000 and use the demo password from your `.env`.

### Required environment variables

| Variable                       | Purpose                                                      |
|--------------------------------|--------------------------------------------------------------|
| `OPENAI_API_KEY`               | Embeddings (always) and chat completion (when LLM_PROVIDER=openai) |
| `PINECONE_API_KEY`             | Vector store for the research corpus                         |
| `OPENAI_PINECONE_INDEX_NAME`   | Pinecone index name to read/write                            |
| `CENSUS_API_KEY`               | CVAP and turnout calculations                                |
| `DEMO_PASSWORD`                | Single shared password for the gate (until SSO is wired)     |
| `DJANGO_SECRET_KEY`            | Django secret                                                |

### Optional

| Variable                | Purpose                                              |
|-------------------------|------------------------------------------------------|
| `LLM_PROVIDER`          | `openai` (default), `anthropic`, `google`, `groq`    |
| `ANTHROPIC_API_KEY`     | If LLM_PROVIDER=anthropic                            |
| `GOOGLE_API_KEY`        | If LLM_PROVIDER=google                               |
| `FEC_API_KEY`           | Live FEC opponent finance lookups                    |
| `LLAMA_CLOUD_API_KEY`   | LlamaParse for PDF ingestion (`bulk_upload.py`)      |
| `DEMO_MODE`             | `1` for deterministic, audience-safe agent outputs   |

---

## How the agents work together

A request like "build me a political plan for GA-07" triggers the **political plan** sequence:

1. **Researcher** pulls relevant memos from Pinecone (general + org).
2. **Election Results** pulls FEC + state data on the district's last 3 cycles.
3. **Opposition Research** (`chat/agents/opposition_research.py`) retrieves the contextual research book for the district. The module name is inherited from earlier work; in nonpartisan use, this agent surfaces public-record context on incumbents and policy positions.
4. **Win Number** calculates votes-to-win from CVAP, historical turnout, and district type.
5. **Precincts** identifies and ranks target precincts with demographic breakdowns.
6. **Messaging** generates five formats (canvass, phone, text, mail, digital), grounded only in steps 1-5.
7. **Cost Calculator** estimates spend using `tool_templates/costs.json` rates.
8. **Synthesizer** assembles the final Markdown/DOCX with citations.

For focused single-topic requests, the orchestrator picks just the one or two agents needed and skips the rest.

### Voter file flow

When a CSV or XLSX is uploaded:

1. **Ingestor** routes the file to the voter file agent.
2. **Voter File Agent** auto-detects the vendor (TargetSmart, Catalist, L2, VAN), standardizes columns, and runs segmentation.
3. **Researcher** pulls best-practices memos for the matched segments.
4. **Messaging** produces segment-specific scripts (Spanish-language for Latinx segments, etc.).
5. **Cost Calculator** estimates the program cost for the segments.
6. **Synthesizer** delivers the segmented plan and (if requested) a CSV export.

---

## Adding to the research corpus

```bash
# Drop your PDFs in research_memos/
python bulk_upload.py research_memos/

# To re-index existing files (e.g. after a metadata schema change):
python bulk_upload.py research_memos/ --force-reindex
```

Best-practices Markdown files in `tool_templates/best_practices/` are also seeded into Pinecone via `python scripts/seed_best_practices.py`. These are the curated field playbooks the messaging agent leans on when no client-specific corpus is available.

## Running tests

```bash
# Live-LLM integration tests (requires keys in .env):
python -m pytest chat/tests/test_agents.py
python -m pytest chat/tests/test_full_pipeline.py

# Voter-file pipeline + agent contract tests (no LLM calls):
python scripts/_validate_demo_voterfile.py
python scripts/_test_language_and_chaining.py
```

## Demo data

A 50,000-row synthetic Gwinnett County, GA voter file lives at `data/demo/gwinnett_demo_voterfile.csv`. It is shaped exactly like a real TargetSmart export and is the recommended file for live demos and screen recordings. Regenerate it any time with `python scripts/generate_demo_voterfile.py`.

For the live demo walkthrough, see [`DEMO.md`](./DEMO.md).

---

## Contributing

Pull requests welcome. Please:

1. Open an issue or @-mention a maintainer before starting on anything larger than a one-file change.
2. Run the validation scripts above before opening a PR.
3. Keep PRs focused: one bug or one feature per PR.
4. New agents go in `chat/agents/` and must read/write only through `AgentState`.
5. New tool templates go in `tool_templates/` as Markdown, no code changes needed.

### Production hardening checklist

- `DEBUG=False` in `.env`
- `ALLOWED_HOSTS` set to your domain(s)
- `/admin/` moved to a non-default path or restricted by IP
- Static files served by `whitenoise` or a CDN
- A real auth system in front of the demo password gate

---

## License

MIT License. See [LICENSE](./LICENSE) for full text.

## Acknowledgments

- **Analyst Institute, CIRCLE (Tufts), Equis Research, Voto Latino, NextGen America**: the public field-research corpus that informs the best-practices set.
- **American Bridge**: research book corpus.
- **TargetSmart, Catalist, L2, VAN**: voter file format references.
