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
./venv/bin/python scripts/_test_social_scripts.py                 # 74 assertions
```

Across the full deterministic suite (18 files in `scripts/_test_*.py`), every test is green on `milestone-h-social-script-pack`.

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

### Deploying to powerbuilder.app

See [`DEPLOY.md`](./DEPLOY.md) for the runbook (SSH into the droplet, `git pull origin main`, `sudo systemctl restart powerbuilder`).

---

## Research basis and design decisions

Powerbuilder is built to be defensible to a c3 nonprofit board. Every interaction surface, every messaging format, and every default behavior traces back to peer-reviewed research, public field experiments, or published industry data. This appendix records the thought process behind milestones A through H so a reviewer can audit not just what the tool does, but why it does it that way.

### Milestone A: demo mode and the deterministic baseline

The demo gate (a `DEMO_MODE=1` flag that swaps live LLM calls for fixed, audience-safe outputs) exists because nonprofit-side demos cannot tolerate hallucinations or randomness on stage. The same logic that makes A/B testing rigorous in field experiments, treating the deliverable as the unit of analysis and removing variance you do not control, applies to a product demo. [Coppock, Hill, and Vavreck (APSR 2024)](https://www.cambridge.org/core/services/aop-cambridge-core/content/view/FF5BE6ED1553475F8321F7C4209357F7/S0003055423001387a.pdf) found that almost no political ad in their meta-analysis moved persuasion outside a tight band, which means the difference between a good demo and a bad one is reliability, not magic. Demo mode lets us promise reliability.

### Milestone B: download cards and mobile polish

We moved exports out of an inline blob and into named, dated download cards because the people who run independent field programs work on phones, in cars, between doors. The choice to surface every artifact (DOCX, CSV, XLSX) as a card, with size and timestamp, mirrors the CRM convention voter-contact staff already use. There is no formal citation here, the rationale is operational: a field director on a Saturday morning needs to grab a walk list in three taps, not scroll through a chat transcript.

### Milestone C: mobile drawer and progressive disclosure

All layout decisions on mobile follow from the observation in [Hackenburg and Margetts (PNAS 2024)](https://pnas.org/doi/10.1073/pnas.2403116121) that microtargeted persuasion produces null effects at scale, while the [TargetSmart Spanish-language analysis](https://targetsmart.com/research-shows-latinx-voters-want-ads-in-spanish-bolstering-the-case-for-more-spending/) shows in-language outreach delivers a 3.9 to 14.5 point turnout lift. Together these say: do not over-personalize copy, do over-invest in language access. The mobile drawer surfaces the language toggle as a first-class control rather than burying it in settings.

### Milestone D: rerun chips and the plan panel

The rerun chip pattern (one tap to regenerate a single agent's output without re-running the whole plan) is informed by [Hackenburg et al. (PNAS 2025)](https://pnas.org/doi/10.1073/pnas.2413443122), which shows LLM persuasion scales logarithmically with model size. Practically, that means the marginal value of regenerating one section with a stronger model is high, while the marginal cost of regenerating an entire plan is low information gain for high spend. Rerun chips let an organizer iterate on the messaging block without paying to re-derive the win number.

### Milestone E: error chips and copy-to-clipboard

Deep-canvassing research (see [Brock-Petroshius and Gilens, JOSI 2025](https://spssi.onlinelibrary.wiley.com/doi/10.1111/josi.70012)) shows that the highest-leverage moments in voter contact are conversational and unscripted, but only when the canvasser has a reliable script to fall back on. The copy-to-clipboard control on every script block, paired with explicit error chips when an agent fails, treats the script as a tool the field staffer owns, not a black box. Errors are surfaced inline so the user can decide whether to retry, swap formats, or proceed with partial output.

### Milestone F: sidebar history, rename, drag-reorder, and source dedup

Multi-session continuity matters because plans evolve over weeks. The [Schein et al. Outvote 2020 study](https://www.ssrn.com/abstract=3696179) found a CACE of about 8.3 percentage points for friend-to-friend texting, the strongest effect size in modern GOTV literature, but only when the relational asks were re-used and refined across cycles. The sidebar (with rename, drag-reorder, and source dedup) treats every plan as an asset that gets re-opened, not a one-off. Source dedup specifically prevents the corpus from showing the same memo five times when five agents all cited it, which preserves the reviewer's ability to audit citations.

### Milestone G: tile config and plan groups

The empty-state demo tiles are a guided onramp for first-time users. Each tile maps to a documented plan group (GA-07 youth, Spanish-language Gwinnett, AAPI multi-language, voter file upload). The plan-grouping logic, four agents minimum (`win_number`, `precincts`, `cost_calculator`, `messaging`) gates a full plan render, codifies the [LULAC 2024 "From Registration to Representation" framework](https://lulac.org/research/From_Registration_to_Representation_Latino_Turnout_as_Path_to_Power/): turnout requires geography, audience, message, and budget held in one frame. Surfacing tiles instead of a blank text box reduces the cold-start cost for an organizer who has never seen the tool before. The teal social-pack tile previewed in this milestone became the entry point for milestone H.

### Milestone H: research-backed social media script pack

Milestone H adds three new messaging formats (Meta post, YouTube script, TikTok or Reels script) on top of the existing five (canvass, phone, text, mail, digital). Each platform variant is shaped by platform-specific findings, not a generic "write a social post" prompt. The decision to ship three discrete formats rather than one flexible one comes from the [Wesleyan Media Project 2024 summary](https://mediaproject.wesleyan.edu/2024-summary-062425/), which documents that Meta and YouTube serve fundamentally different strategic functions in modern campaigns: Meta is a mobilization engine, YouTube is a persuasion engine. Treating them as one format would erase that distinction.

**Meta post.** Mobilization frame, kitchen-table economic anchor, identity-as-noun call to action, body under 280 characters. The mobilization frame follows Wesleyan 2024 and the [Tech for Campaigns 2024 digital ads report](https://www.techforcampaigns.org/results/2024-digital-ads-report), which found mobilization-themed creative on issues like abortion access cost 1.8 to 5 times less per outcome than persuasion-themed creative on the same platforms. The kitchen-table economic frame comes from the [Priorities USA AAPI voter memo (2022)](https://priorities.org/wp-content/uploads/2022/10/AAPI-voter-memo-.pdf), which found pocketbook framing outperformed identity framing among AAPI voters by double digits. The identity-as-noun construction ("be a voter" rather than "go vote") comes from [Bryan, Walton, Rogers, and Dweck (PNAS 2011)](https://pmc.ncbi.nlm.nih.gov/articles/PMC3150938/), which found a roughly 11-point turnout boost from the noun framing alone.

**YouTube script.** A 60 to 90 second persuasion script with explicit timestamp markers (`0:00` hook, `0:05` evidence, `0:30` contrast, `0:55` ask). Length and structure are calibrated to Wesleyan 2024's finding that YouTube is the dominant persuasion channel and to the social-pressure mechanism documented in [Bond et al. (Nature 2012)](https://pmc.ncbi.nlm.nih.gov/articles/PMC3834737/), which found that a 61-million-person Facebook social-pressure experiment moved roughly 340,000 votes, primarily through visible peer behavior rather than informational content. A YouTube script that ends on a peer-visible action ask is doing what the literature says works.

**TikTok or Reels script.** A 15 to 30 second attention-first script with no party logos, lifestyle-wrapped politainment, and an ending question to invite duet or stitch responses. Format and tone come from [Chmel, Kim, Marshall, and Lubin (2024)](https://www.semanticscholar.org/paper/09e280bae78202b0f5ea04110691b8f6fd714dfe), which found that creator-led content outperforms traditional outreach by wide margins on short-form vertical platforms, and from the [Harvard Kennedy School Misinformation Review 2024 TikTok analysis](https://misinforeview.hks.harvard.edu/article/toxic-politics-and-tiktok-engagement-in-the-2024-u-s-election/), which documented that overtly partisan content was more likely to be flagged or down-ranked, while lifestyle-wrapped content reached comparable audiences without the penalty. Tech for Campaigns 2024 separately found that micro-influencer content delivered 5 to 9 times the engagement lift of equivalently spent paid media.

**Length and hook checks.** Each generated variant is post-processed by `check_social_format()`, which annotates the output with a `*Format check:*` line if the body exceeds platform limits (Meta 900 characters, YouTube 2200, TikTok 900) or if the opener uses one of ten flat opener patterns ("In today's world," "Let me tell you about," etc.). The flat-opener list is informed by the attention-curve evidence in [Aggarwal et al. (Nature Human Behaviour 2023)](https://www.nature.com/articles/s41562-022-01487-4), a 2-million-person digital-ad experiment that found the first three seconds of creative drove the bulk of measured persuasion lift.

**In-language captions.** Every variant supports a Spanish or Vietnamese caption toggle. The Spanish path is grounded in TargetSmart's 3.9 to 14.5 point turnout lift finding and in [Cisneros et al. (PNAS Nexus 2024)](https://pmc.ncbi.nlm.nih.gov/articles/PMC11561907/), which found that Spanish-language misinformation exposure raised vote-switching intent by 11 points; the rebuttal pattern in our caption template is structured to inoculate against the specific misinformation frames Cisneros et al. catalogued.

### What we deliberately did not build

Based on [Hackenburg and Margetts (PNAS 2024)](https://pnas.org/doi/10.1073/pnas.2403116121), Powerbuilder does not offer narrow microtargeting features (psychographic match, individual-level persuasion scores). The evidence for null effects is strong enough that shipping those features would be selling a result the literature does not support. We surface segment-level targeting (age cohort, language, geography, propensity) and stop there.

### Future milestones (proposed)

- Milestone I, creator and influencer match agent, picks up the Chmel et al. finding directly.
- Milestone J, relational organizing pack, operationalizes the Schein et al. CACE.
- Milestone K, A/B test scaffolding, builds on Coppock et al.
- Milestone L, mobilization vs. persuasion mode toggle, formalizes the Wesleyan 2024 distinction across all formats.
- Milestone M, Spanish-language misinformation rebuttal mode, extends Cisneros et al. into a first-class agent.

---

## License

MIT License. See [LICENSE](./LICENSE) for full text.

## Acknowledgments

- **Analyst Institute, CIRCLE (Tufts), Equis Research, Voto Latino, NextGen America**: the public field-research corpus that informs the best-practices set.
- **American Bridge**: research book corpus.
- **TargetSmart, Catalist, L2, VAN**: voter file format references.
