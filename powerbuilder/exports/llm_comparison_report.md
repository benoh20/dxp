# Powerbuilder LLM Provider Comparison Report

**Generated:** 2026-04-15 19:21:30  
**Providers tested:** anthropic, gemini, openai  
**Queries:** 3  

---

## Anthropic

| Field | Value |
|-------|-------|
| Completion model | `claude-sonnet-4-5` |
| Embedding model  | `openai (fallback)` |
| Pinecone index   | `powerbuilder-openai` |

### Q1: Young voter targeting + messaging

> *I want to reach young voters in Virginia's 7th Congressional District. What precincts should I target and what message should I deliver?*

**Error:** `Index 'powerbuilder-openai' does not exist. Run comparison_ingestor.py first.`

### Q2: Canvassing cost estimate

> *How much would it cost to run a canvassing program in Virginia's 7th Congressional District in 2026?*

**Error:** `Index 'powerbuilder-openai' does not exist. Run comparison_ingestor.py first.`

### Q3: Win number

> *What is the win number for Virginia's 7th Congressional District in 2026?*

**Error:** `Index 'powerbuilder-openai' does not exist. Run comparison_ingestor.py first.`

---

## Gemini

| Field | Value |
|-------|-------|
| Completion model | `gemini-1.5-pro` |
| Embedding model  | `models/text-embedding-004` |
| Pinecone index   | `powerbuilder-google` |

### Q1: Young voter targeting + messaging

> *I want to reach young voters in Virginia's 7th Congressional District. What precincts should I target and what message should I deliver?*

**Error:** `Index 'powerbuilder-google' does not exist. Run comparison_ingestor.py first.`

### Q2: Canvassing cost estimate

> *How much would it cost to run a canvassing program in Virginia's 7th Congressional District in 2026?*

**Error:** `Index 'powerbuilder-google' does not exist. Run comparison_ingestor.py first.`

### Q3: Win number

> *What is the win number for Virginia's 7th Congressional District in 2026?*

**Error:** `Index 'powerbuilder-google' does not exist. Run comparison_ingestor.py first.`

---

## Openai

| Field | Value |
|-------|-------|
| Completion model | `gpt-4o` |
| Embedding model  | `text-embedding-3-small` |
| Pinecone index   | `powerbuilder-openai` |

### Q1: Young voter targeting + messaging

> *I want to reach young voters in Virginia's 7th Congressional District. What precincts should I target and what message should I deliver?*

**Error:** `Index 'powerbuilder-openai' does not exist. Run comparison_ingestor.py first.`

### Q2: Canvassing cost estimate

> *How much would it cost to run a canvassing program in Virginia's 7th Congressional District in 2026?*

**Error:** `Index 'powerbuilder-openai' does not exist. Run comparison_ingestor.py first.`

### Q3: Win number

> *What is the win number for Virginia's 7th Congressional District in 2026?*

**Error:** `Index 'powerbuilder-openai' does not exist. Run comparison_ingestor.py first.`

---

## ChangeAgent

ChangeAgent: pending API integration

_This section will be populated automatically once ChangeAgent is registered via `register_custom_provider()` in llm_config.py._

---

## Timing Summary

| Provider | Query | Retrieval | Completion | Total |
|----------|-------|-----------|------------|-------|
