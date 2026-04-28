# Powerbuilder

**An AI-orchestrated civic engagement platform for nonpartisan voter outreach, education, and field operations.**

Powerbuilder is a Django + LangGraph application that coordinates a team of specialist AI agents (researcher, win-number, precincts, messaging, opposition research, voter-file analyst, and more) to generate full civic engagement plans, segment-targeted messaging, and budget estimates from a single natural-language request. The current public deployment lives at [powerbuilder.app](https://powerbuilder.app).

Built by [Benjamin Oh](https://github.com/benoh20) and [Rosario Palacios](https://github.com/Mdr-palacios) as part of the **DxP Fellowship**.

---

## What it does

An organizer or program manager types a request in plain English (or Spanish):

> "Build me a Gwinnett County GOTV plan targeting Latinx voters 18-35 with a Spanish door-knock script and a CSV export."

Powerbuilder routes the request through a LangGraph orchestrator that decides which specialist agents to call, in what order. Each agent writes its findings back to a shared whiteboard (`AgentState`). A synthesizer agent assembles the final deliverable (Markdown, DOCX, or CSV), grounded in research drawn from a curated Pinecone-backed corpus and live data sources (US Census, FEC, ChangeAgent).

## Why it exists

Most civic technology is sold to large institutions and staffed by analysts. The independent organizer, the community-based field program, and the local nonpartisan voter education effort rarely have access to the same caliber of strategic planning or research synthesis. Powerbuilder exists to close that gap with software that does the work of a junior strategist, a research analyst, and a field director, without replacing any of them.

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
- **`chat/agents/finance_agent.py`** + **`chat/agents/paid_media.py`**: cost calculator with two layers. The base layer prices door, phone, text, mail, and digital contacts against per-contact unit costs and FEC historical comparables. The paid-media layer (`paid_media.py`, codified from corpus file 07) builds a deterministic digital plan when a budget is set: 4 spend tiers, in-language CPM discount (22.5 percent), frequency-cap-based reach math, persuasion-point lift estimates, and a saturation cap that fires when the planned digital reach would exceed the persuadable universe.
- **`chat/agents/export.py`**: synthesizer plus DOCX/CSV/XLSX renderer. Plan runs always emit a styled DOCX (Light Grid Accent 1 tables for win number, target precincts, per-contact rates, and the paid-media digital channel rollup) alongside a CSV companion of the target precinct list, so an operator gets both the strategy doc and the walk/call list from one chat turn.
- **`tool_templates/`**: editable Markdown templates for each output format (canvass scripts, phone scripts, etc.) plus `costs.json` for cost-per-contact rates. Drop a new `.md` in here to change copy structure without touching code.
- **`tool_templates/best_practices/`**: 10 curated field-research files (Latinx GOTV, Spanish messaging norms, new-registrant outreach, contact-channel mix, Gen Z, Gwinnett context, paid-media digital benchmarks, AAPI multi-language outreach, AAPI extended languages, and rural and exurban organizing). Seeded into Pinecone via `python scripts/seed_best_practices.py`. The same script writes a local fallback index (`scripts/.local_corpus_index.json`) so the researcher keeps working in dev when Pinecone is unreachable.

### Data isolation

Every Pinecone read and write is scoped to an `org_namespace` derived from the authenticated user's email domain. The `__default__` namespace holds the curated public corpus (American Bridge research books, Analyst Institute briefs, the Powerbuilder best-practices set). Per-org uploads never leave their namespace.

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

1. **Researcher** pulls relevant memos from Pinecone (general + org), or from the local fallback index when Pinecone is unreachable.
2. **Election Results** pulls FEC + state data on the district's last 3 cycles.
3. **Opposition Research** (`chat/agents/opposition_research.py`) retrieves the contextual research book for the district. The module name is inherited from earlier work; in nonpartisan use, this agent surfaces public-record context on incumbents and policy positions.
4. **Win Number** calculates votes-to-win from CVAP, historical turnout, and district type. It also derives a **persuadable universe**, taking the smaller of (a) 20 percent of projected turnout, (b) 2.5 times the win-number cushion, capped at projected turnout. Downstream agents read this as the addressable swing audience.
5. **Precincts** identifies and ranks target precincts with demographic breakdowns.
6. **Messaging** generates five formats (canvass, phone, text, mail, digital), grounded only in steps 1-5.
7. **Cost Calculator** estimates spend using `tool_templates/costs.json` rates. When a total program budget is set, it also builds a **paid-media plan** (channel mix, CPMs with in-language discount, impressions, reach capped at the persuadable universe, and persuasion-point lift estimates) from corpus file 07.
8. **Synthesizer** assembles the deliverable, emitting a styled DOCX (with the paid-media plan rendered as a styled subsection under Budget Estimate) and a CSV companion of the target precincts.

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

Best-practices Markdown files in `tool_templates/best_practices/` are also seeded into Pinecone via `python scripts/seed_best_practices.py`. These are the curated field playbooks the messaging agent leans on when no client-specific corpus is available. Adding a new file is a drop-in: write a frontmatter block (source, date, document type, topics), the body, then re-run the seed script. The script prints chunks-per-file and writes both a Pinecone upload (when reachable) and a local fallback index for development.

The seed script is self-bootstrapping. If `OPENAI_PINECONE_INDEX_NAME` does not yet exist on the configured Pinecone account, the script creates it as a serverless cosine index (1536 dims, aws/us-east-1 by default; override with `PINECONE_CLOUD` and `PINECONE_REGION`) and waits for it to be ready before upserting. After upsert, it verifies three things: (a) the namespace vector count matches the upload size, (b) a known vector ID round-trips through fetch, and (c) a small set of smoke-test queries each return the expected source file in the top 3. Failed checks exit non-zero, so a half-seeded index never goes unnoticed. Pass `--skip-verify` to bypass post-upload checks (not recommended).

## Running tests

```bash
# Live-LLM integration tests (requires keys in .env):
python -m pytest chat/tests/test_agents.py
python -m pytest chat/tests/test_full_pipeline.py

# Voter-file pipeline + agent contract tests (no LLM calls):
python scripts/_validate_demo_voterfile.py
python scripts/_test_language_and_chaining.py
```

The demo-mode hardening branch ships a focused suite of deterministic tests that run without keys, without network, and without Django request mocking. They cover the parts of the pipeline most likely to silently regress:

```bash
cd powerbuilder
./venv/bin/python scripts/_test_demo_voterfile_autoload.py        # 4 assertions
./venv/bin/python scripts/_test_export_csv_companion.py           # 5 assertions
./venv/bin/python scripts/_test_local_corpus_fallback.py          # 13 assertions
./venv/bin/python scripts/_test_paid_media_estimator.py           # 11 assertions
./venv/bin/python scripts/_test_export_paid_media_docx.py         # 6 assertions
./venv/bin/python scripts/_test_persuadable_universe_wiring.py    # 9 assertions
./venv/bin/python scripts/_test_seed_verification.py              # 9 assertions
```

57 assertions total; all green on `demo-mode-and-hardening`.

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
