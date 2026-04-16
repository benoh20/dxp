# Powerbuilder LLM Provider Comparison Report

**Generated:** 2026-04-16 16:24:02  
**Providers tested:** anthropic, cohere, gemini, groq, llama, mistral, openai  
**Queries:** 3  

---

## Anthropic

| Field | Value |
|-------|-------|
| Completion model | `claude-sonnet-4-5` |
| Embedding model  | `openai (fallback)` |
| Pinecone index   | `powerbuilder-anthropic` |

### Q1: Young voter targeting + messaging

> *I want to reach young voters in Virginia's 7th Congressional District. What precincts should I target and what message should I deliver?*

**Retrieval** (3.48s)  
Sources: HIT_Countering Racialized Politics About Crime in 2024.pdf, HIT_Countering Racialized Politics About Crime in 2024.pdf, HIT_Countering Racialized Politics About Crime in 2024.pdf, HIT_Countering Racialized Politics About Crime in 2024.pdf, HIT_Headcount_Public-Memo.pdf

1. _ VeraAcTION 6 # Overview of the Ad Test  • Virginia is an excellent off-year bellwether, and in the 2023 cycle, the GOP spent over $25 million on ads there attacking Democrats as "soft on crime."  • R_
2. _ VeraAcTION 6 # Overview of the Ad Test  • Virginia is an excellent off-year bellwether, and in the 2023 cycle, the GOP spent over $25 million on ads there attacking Democrats as "soft on crime."  • R_
3. _ ©HITstrategies                            VeraAcTION  # Future Research Recommendations:  - Understanding how this messaging tests with voters across battleground states. - Finding more clarity on vo_
4. _ ©HITstrategies                            VeraAcTION  # Future Research Recommendations:  - Understanding how this messaging tests with voters across battleground states. - Finding more clarity on vo_
5. _ HITstrategies HEADCOUNT  # Young registered voters aged 18-34 exhibit different voting behavior based on their top issue and their media sources.  TO: Interested Parties  FROM: HIT Strategies, HeadCo_

**Completion** (4.74s)  

I cannot answer this question based on the research context provided. The documents discuss crime messaging strategies in Virginia's 2023 elections and a national survey of young voters, but they do not contain information about specific precincts in Virginia's 7th Congressional District or targeted messaging recommendations for that district. To answer your question, you would need precinct-level voting data and demographic analysis specific to VA-07.

### Q2: Canvassing cost estimate

> *How much would it cost to run a canvassing program in Virginia's 7th Congressional District in 2026?*

**Retrieval** (3.76s)  
Sources: HIT_Countering Racialized Politics About Crime in 2024.pdf, HIT_Countering Racialized Politics About Crime in 2024.pdf, Equis_2025 Elections and New Equis Polling_October.pdf, Equis_2025 Elections and New Equis Polling_October.pdf, Equis_2025 Elections and New Equis Polling_October.pdf

1. _ VeraAcTION 6 # Overview of the Ad Test  • Virginia is an excellent off-year bellwether, and in the 2023 cycle, the GOP spent over $25 million on ads there attacking Democrats as "soft on crime."  • R_
2. _ VeraAcTION 6 # Overview of the Ad Test  • Virginia is an excellent off-year bellwether, and in the 2023 cycle, the GOP spent over $25 million on ads there attacking Democrats as "soft on crime."  • R_
3. _ # Equis Pulsecheck Wave 2: Frequencies, October 15-29, 2025  # Q.9  I know it's a long way off, but if the November 2026 election for U.S. Congress were held today, for whom would you vote - the Demo_
4. _ # Equis Pulsecheck Wave 2: Frequencies, October 15-29, 2025  # Q.9  I know it's a long way off, but if the November 2026 election for U.S. Congress were held today, for whom would you vote - the Demo_
5. _ # Equis Pulsecheck Wave 2: Frequencies, October 15-29, 2025  # Q.9  I know it's a long way off, but if the November 2026 election for U.S. Congress were held today, for whom would you vote - the Demo_

**Completion** (3.17s)  

I cannot answer this question based on the provided research context. The documents discuss crime messaging strategies and polling data, but do not contain information about the costs of running canvassing programs in Virginia's 7th Congressional District or any other district.

### Q3: Win number

> *What is the win number for Virginia's 7th Congressional District in 2026?*

**Retrieval** (3.65s)  
Sources: Equis_2025 Elections and New Equis Polling_October.pdf, Equis_2025 Elections and New Equis Polling_October.pdf, Equis_2025 Elections and New Equis Polling_October.pdf, Equis_2025 Elections and New Equis Polling_October.pdf, HIT_Countering Racialized Politics About Crime in 2024.pdf

1. _ # Equis Pulsecheck Wave 2: Frequencies, October 15-29, 2025  # Q.9  I know it's a long way off, but if the November 2026 election for U.S. Congress were held today, for whom would you vote - the Demo_
2. _ # Equis Pulsecheck Wave 2: Frequencies, October 15-29, 2025  # Q.9  I know it's a long way off, but if the November 2026 election for U.S. Congress were held today, for whom would you vote - the Demo_
3. _ # Equis Pulsecheck Wave 2: Frequencies, October 15-29, 2025  # Q.9  I know it's a long way off, but if the November 2026 election for U.S. Congress were held today, for whom would you vote - the Demo_
4. _ # Equis Pulsecheck Wave 2: Frequencies, October 15-29, 2025  # Q.9  I know it's a long way off, but if the November 2026 election for U.S. Congress were held today, for whom would you vote - the Demo_
5. _ VeraAcTION 6 # Overview of the Ad Test  • Virginia is an excellent off-year bellwether, and in the 2023 cycle, the GOP spent over $25 million on ads there attacking Democrats as "soft on crime."  • R_

**Completion** (3.77s)  

Based on the research context provided, I cannot answer this question. The documents include polling data from the Equis Pulsecheck Wave 2 (October 2025) showing generic congressional ballot preferences, and information about crime-related political advertising in Virginia, but neither source provides specific win number projections for Virginia's 7th Congressional District in 2026.

---

## Cohere

| Field | Value |
|-------|-------|
| Completion model | `command-r-plus` |
| Embedding model  | `embed-english-v3.0` |
| Pinecone index   | `powerbuilder-cohere` |

### Q1: Young voter targeting + messaging

> *I want to reach young voters in Virginia's 7th Congressional District. What precincts should I target and what message should I deliver?*

**Error:** `Completion failed: headers: {'access-control-expose-headers': 'X-Debug-Trace-ID', 'cache-control': 'no-cache, no-store, no-transform, must-revalidate, private, max-age=0', 'content-encoding': 'gzip', 'content-type': 'application/json', 'expires': 'Thu, 01 Jan 1970 00:00:00 GMT', 'pragma': 'no-cache', 'vary': 'Origin,Accept-Encoding', 'x-accel-expires': '0', 'x-debug-trace-id': 'f2dd389ebfa9ffccf5b3702d355a02d2', 'x-endpoint-monthly-call-limit': '1000', 'x-trial-endpoint-call-limit': '20', 'x-trial-endpoint-call-remaining': '19', 'date': 'Thu, 16 Apr 2026 20:25:01 GMT', 'x-envoy-upstream-service-time': '10', 'server': 'envoy', 'via': '1.1 google', 'alt-svc': 'h3=":443"; ma=2592000', 'transfer-encoding': 'chunked'}, status_code: 404, body: {'id': '876f85c1-37ea-4bb5-9dbc-f644fabf74d1', 'message': "model 'command-r-plus' was removed on September 15, 2025. See https://docs.cohere.com/docs/models#command for a list of models you can use instead."}`

### Q2: Canvassing cost estimate

> *How much would it cost to run a canvassing program in Virginia's 7th Congressional District in 2026?*

**Error:** `Completion failed: headers: {'access-control-expose-headers': 'X-Debug-Trace-ID', 'cache-control': 'no-cache, no-store, no-transform, must-revalidate, private, max-age=0', 'content-encoding': 'gzip', 'content-type': 'application/json', 'expires': 'Thu, 01 Jan 1970 00:00:00 GMT', 'pragma': 'no-cache', 'vary': 'Origin,Accept-Encoding', 'x-accel-expires': '0', 'x-debug-trace-id': 'f08747754039647fa04012c2f32bdaa2', 'x-endpoint-monthly-call-limit': '1000', 'x-trial-endpoint-call-limit': '20', 'x-trial-endpoint-call-remaining': '18', 'date': 'Thu, 16 Apr 2026 20:25:01 GMT', 'x-envoy-upstream-service-time': '4', 'server': 'envoy', 'via': '1.1 google', 'alt-svc': 'h3=":443"; ma=2592000', 'transfer-encoding': 'chunked'}, status_code: 404, body: {'id': 'f81413a2-2e91-4500-8186-6a3922198d22', 'message': "model 'command-r-plus' was removed on September 15, 2025. See https://docs.cohere.com/docs/models#command for a list of models you can use instead."}`

### Q3: Win number

> *What is the win number for Virginia's 7th Congressional District in 2026?*

**Error:** `Completion failed: headers: {'access-control-expose-headers': 'X-Debug-Trace-ID', 'cache-control': 'no-cache, no-store, no-transform, must-revalidate, private, max-age=0', 'content-encoding': 'gzip', 'content-type': 'application/json', 'expires': 'Thu, 01 Jan 1970 00:00:00 GMT', 'pragma': 'no-cache', 'vary': 'Origin,Accept-Encoding', 'x-accel-expires': '0', 'x-debug-trace-id': '0e7129f1c84be99a1cca4ba23a66d0d0', 'x-endpoint-monthly-call-limit': '1000', 'x-trial-endpoint-call-limit': '20', 'x-trial-endpoint-call-remaining': '17', 'date': 'Thu, 16 Apr 2026 20:25:01 GMT', 'x-envoy-upstream-service-time': '6', 'server': 'envoy', 'via': '1.1 google', 'alt-svc': 'h3=":443"; ma=2592000,h3-29=":443"; ma=2592000', 'transfer-encoding': 'chunked'}, status_code: 404, body: {'id': '7a1e934c-6fba-4176-b66b-73a6193596b7', 'message': "model 'command-r-plus' was removed on September 15, 2025. See https://docs.cohere.com/docs/models#command for a list of models you can use instead."}`

---

## Gemini

| Field | Value |
|-------|-------|
| Completion model | `gemini-2.5-flash` |
| Embedding model  | `models/gemini-embedding-001` |
| Pinecone index   | `research-index` |

### Q1: Young voter targeting + messaging

> *I want to reach young voters in Virginia's 7th Congressional District. What precincts should I target and what message should I deliver?*

**Retrieval** (2.67s)  
Sources: HIT_Headcount_Public-Memo.pdf, HIT_Countering Racialized Politics About Crime in 2024.pdf, HIT_Headcount_Public-Memo.pdf, HIT_Countering Racialized Politics About Crime in 2024.pdf, HIT_Countering Racialized Politics About Crime in 2024.pdf

1. _ HEADCOUNT  # Survey Methodology:  These findings are from a proprietary survey conducted by HIT Strategies and HeadCount. This survey consisted of 1000 registered voters ages 18-35 nationwide. The su_
2. _ VeraAcTION 6 # Overview of the Ad Test  • Virginia is an excellent off-year bellwether, and in the 2023 cycle, the GOP spent over $25 million on ads there attacking Democrats as "soft on crime."  • R_
3. _ HITstrategies HEADCOUNT  # Young registered voters aged 18-34 exhibit different voting behavior based on their top issue and their media sources.  TO: Interested Parties  FROM: HIT Strategies, HeadCo_
4. _ VeraActIon # Overview of the Ad Test  • Virginia is an excellent off-year bellwether, and in the 2023 cycle, the GOP spent over $25 million on ads there attacking Democrats as "soft on crime."  • ove_
5. _  # Methodology  # VeraAcTION 5  | Universe        | Sample Size        | Methodology                                                                                                                   _

**Completion** (4.82s)  

The provided context does not specify particular precincts within Virginia's 7th Congressional District to target. However, to reach young voters (18-35), your message should emphasize their vote's power to create change on issues important to them, as they are not a monolithic group. Regarding public safety, a "serious about safety" platform that includes gun safety measures is effective, as 52% of respondents overwhelmingly called out increased gun safety. Avoid "blood on the streets" hyperbole, which does not perform well outside the GOP base.

### Q2: Canvassing cost estimate

> *How much would it cost to run a canvassing program in Virginia's 7th Congressional District in 2026?*

**Retrieval** (2.66s)  
Sources: HIT_Winning Jobs Narrative_2022.pdf, HIT_Headcount_Public-Memo.pdf, HIT_Winning Jobs Narrative_2022.pdf, HIT_Countering Racialized Politics About Crime in 2024.pdf, Equis_2025 Elections and New Equis Polling_October.pdf

1. _  # INTRODUCTION  # About the Project  # HITstrategies  # Phase 3  # Field/Ethnographic Research  Report(S) available at https://www.winningjobsnarrative.org  # November 2021 - March 2022  2,503 Deep _
2. _ HEADCOUNT  # Survey Methodology:  These findings are from a proprietary survey conducted by HIT Strategies and HeadCount. This survey consisted of 1000 registered voters ages 18-35 nationwide. The su_
3. _  # INTRODUCTION  # About the Project  ©HITstrategies  # Phase 3  # Field/Ethnographic Research  Report(S) available at https://www.winningjobsnarrative.org  November 2021 - March 2022  2,503 Deep Can_
4. _  # Methodology  # VeraActiOn 5  | Universe        | Sample Size        | Methodology                                                                                                                   _
5. _ # Equis Pulsecheck Wave 2: Frequencies, October 15-29, 2025  # Q.9  I know it's a long way off, but if the November 2026 election for U.S. Congress were held today, for whom would you vote - the Demo_

**Completion** (4.24s)  

The provided research context does not contain information regarding the cost of running a canvassing program. While it details deep canvassing conversations conducted in five states (AK, KY, MI, NC, PA) between November 2021 and March 2022, it does not specify any associated expenditures. Furthermore, there is no mention of Virginia's 7th Congressional District within the given documents. Therefore, the cost cannot be determined from this context.

### Q3: Win number

> *What is the win number for Virginia's 7th Congressional District in 2026?*

**Retrieval** (1.27s)  
Sources: Equis_2025 Elections and New Equis Polling_October.pdf, Equis_2025 Elections and New Equis Polling_October.pdf, HIT_Countering Racialized Politics About Crime in 2024.pdf, HIT_Countering Racialized Politics About Crime in 2024.pdf, HIT_Countering Racialized Politics About Crime in 2024.pdf

1. _ # Equis Pulsecheck Wave 2: Frequencies, October 15-29, 2025  # Q.9  I know it's a long way off, but if the November 2026 election for U.S. Congress were held today, for whom would you vote - the Demo_
2. _ # Equis Pulsecheck Wave 2: Frequencies, October 15-29, 2025  # Q.9  I know it's a long way off, but if the November 2026 election for U.S. Congress were held today, for whom would you vote - the Demo_
3. _  # Methodology  # VeraActiOn 5  | Universe        | Sample Size        | Methodology                                                                                                                   _
4. _  # Methodology  # VeraAcTION 5  | Universe        | Sample Size        | Methodology                                                                                                                   _
5. _ VeraAcTION 6 # Overview of the Ad Test  • Virginia is an excellent off-year bellwether, and in the 2023 cycle, the GOP spent over $25 million on ads there attacking Democrats as "soft on crime."  • R_

**Completion** (16.92s)  

The provided research context does not contain information regarding the win number for Virginia's 7th Congressional District in 2026. The Equis polling data is national for the 2026 U.S. Congress election, not district-specific. The Vera Action documents discuss ad testing in Virginia for the 2023 cycle in other areas (Loudoun County, Hampton Roads), without mentioning VA-07 or specific win thresholds for 2026.

---

## Groq

| Field | Value |
|-------|-------|
| Completion model | `llama-3.1-70b-versatile` |
| Embedding model  | `openai (fallback)` |
| Pinecone index   | `openai-research-index` |

### Q1: Young voter targeting + messaging

> *I want to reach young voters in Virginia's 7th Congressional District. What precincts should I target and what message should I deliver?*

**Error:** `Completion failed: Error code: 400 - {'error': {'message': 'The model `llama-3.1-70b-versatile` has been decommissioned and is no longer supported. Please refer to https://console.groq.com/docs/deprecations for a recommendation on which model to use instead.', 'type': 'invalid_request_error', 'code': 'model_decommissioned'}}`

### Q2: Canvassing cost estimate

> *How much would it cost to run a canvassing program in Virginia's 7th Congressional District in 2026?*

**Error:** `Completion failed: Error code: 400 - {'error': {'message': 'The model `llama-3.1-70b-versatile` has been decommissioned and is no longer supported. Please refer to https://console.groq.com/docs/deprecations for a recommendation on which model to use instead.', 'type': 'invalid_request_error', 'code': 'model_decommissioned'}}`

### Q3: Win number

> *What is the win number for Virginia's 7th Congressional District in 2026?*

**Error:** `Completion failed: Error code: 400 - {'error': {'message': 'The model `llama-3.1-70b-versatile` has been decommissioned and is no longer supported. Please refer to https://console.groq.com/docs/deprecations for a recommendation on which model to use instead.', 'type': 'invalid_request_error', 'code': 'model_decommissioned'}}`

---

## Llama

| Field | Value |
|-------|-------|
| Completion model | `llama-3.1-70b-versatile` |
| Embedding model  | `BAAI/bge-base-en-v1.5` |
| Pinecone index   | `research-index` |

### Q1: Young voter targeting + messaging

> *I want to reach young voters in Virginia's 7th Congressional District. What precincts should I target and what message should I deliver?*

**Error:** `Retrieval failed: LLAMA_API_KEY is required for Llama embeddings via Together.ai.`

### Q2: Canvassing cost estimate

> *How much would it cost to run a canvassing program in Virginia's 7th Congressional District in 2026?*

**Error:** `Retrieval failed: LLAMA_API_KEY is required for Llama embeddings via Together.ai.`

### Q3: Win number

> *What is the win number for Virginia's 7th Congressional District in 2026?*

**Error:** `Retrieval failed: LLAMA_API_KEY is required for Llama embeddings via Together.ai.`

---

## Mistral

| Field | Value |
|-------|-------|
| Completion model | `mistral-large-latest` |
| Embedding model  | `mistral-embed` |
| Pinecone index   | `powerbuilder-mistral` |

### Q1: Young voter targeting + messaging

> *I want to reach young voters in Virginia's 7th Congressional District. What precincts should I target and what message should I deliver?*

**Error:** `Index 'powerbuilder-mistral' does not exist. Run comparison_ingestor.py first.`

### Q2: Canvassing cost estimate

> *How much would it cost to run a canvassing program in Virginia's 7th Congressional District in 2026?*

**Error:** `Index 'powerbuilder-mistral' does not exist. Run comparison_ingestor.py first.`

### Q3: Win number

> *What is the win number for Virginia's 7th Congressional District in 2026?*

**Error:** `Index 'powerbuilder-mistral' does not exist. Run comparison_ingestor.py first.`

---

## Openai

| Field | Value |
|-------|-------|
| Completion model | `gpt-4o` |
| Embedding model  | `text-embedding-3-small` |
| Pinecone index   | `openai-research-index` |

### Q1: Young voter targeting + messaging

> *I want to reach young voters in Virginia's 7th Congressional District. What precincts should I target and what message should I deliver?*

**Retrieval** (3.82s)  
Sources: HIT_Countering Racialized Politics About Crime in 2024.pdf, HIT_Countering Racialized Politics About Crime in 2024.pdf, HIT_Headcount_Public-Memo.pdf, HIT_Countering Racialized Politics About Crime in 2024.pdf, HIT_Countering Racialized Politics About Crime in 2024.pdf

1. _ VeraAcTION 6 # Overview of the Ad Test  • Virginia is an excellent off-year bellwether, and in the 2023 cycle, the GOP spent over $25 million on ads there attacking Democrats as "soft on crime."  • R_
2. _ ©HITstrategies                            VeraAcTION  # Future Research Recommendations:  - Understanding how this messaging tests with voters across battleground states. - Finding more clarity on vo_
3. _ HITstrategies HEADCOUNT  # Young registered voters aged 18-34 exhibit different voting behavior based on their top issue and their media sources.  TO: Interested Parties  FROM: HIT Strategies, HeadCo_
4. _ ©HITstrategies                            VeraAcTION  # Future Research Recommendations:  - Understanding how this messaging tests with voters across battleground states. - Finding more clarity on vo_
5. _ VeraActIon # Overview of the Ad Test  • Virginia is an excellent off-year bellwether, and in the 2023 cycle, the GOP spent over $25 million on ads there attacking Democrats as "soft on crime."  • ove_

**Completion** (2.26s)  

To effectively reach young voters in Virginia's 7th Congressional District, focus on precincts with higher concentrations of young registered voters, particularly those in urban and suburban areas where younger demographics are more prevalent. Tailor your message to emphasize the power of their vote in driving change on issues they care about, such as public safety and gun control, as these resonate with young voters. Highlight a comprehensive "serious about safety" platform that addresses both immediate concerns and long-term policy goals, ensuring that the messaging is nuanced and avoids hyperbole, as this approach has shown to be more effective outside of the GOP base.

### Q2: Canvassing cost estimate

> *How much would it cost to run a canvassing program in Virginia's 7th Congressional District in 2026?*

**Retrieval** (3.92s)  
Sources: HIT_Countering Racialized Politics About Crime in 2024.pdf, Equis_2025 Elections and New Equis Polling_October.pdf, Equis_2025 Elections and New Equis Polling_October.pdf, HIT_Countering Racialized Politics About Crime in 2024.pdf, HIT_Countering Racialized Politics About Crime in 2024.pdf

1. _ VeraAcTION 6 # Overview of the Ad Test  • Virginia is an excellent off-year bellwether, and in the 2023 cycle, the GOP spent over $25 million on ads there attacking Democrats as "soft on crime."  • R_
2. _ # Equis Pulsecheck Wave 2: Frequencies, October 15-29, 2025  # Q.9  I know it's a long way off, but if the November 2026 election for U.S. Congress were held today, for whom would you vote - the Demo_
3. _ # Equis Pulsecheck Wave 2: Frequencies, October 15-29, 2025  # Q.9  I know it's a long way off, but if the November 2026 election for U.S. Congress were held today, for whom would you vote - the Demo_
4. _  # Methodology  # VeraActiOn 5  | Universe        | Sample Size        | Methodology                                                                                                                   _
5. _  # Methodology  # VeraAcTION 5  | Universe        | Sample Size        | Methodology                                                                                                                   _

**Completion** (1.38s)  

The provided context does not include specific information about the cost of running a canvassing program in Virginia's 7th Congressional District in 2026. To determine the cost, you would need to consider factors such as the size of the district, the number of canvassers required, the duration of the program, and logistical expenses like transportation and materials. Additionally, historical data on similar programs and current market rates for canvassing services would be necessary to provide an accurate estimate.

### Q3: Win number

> *What is the win number for Virginia's 7th Congressional District in 2026?*

**Retrieval** (3.65s)  
Sources: Equis_2025 Elections and New Equis Polling_October.pdf, Equis_2025 Elections and New Equis Polling_October.pdf, HIT_Countering Racialized Politics About Crime in 2024.pdf, Equis_2025 Elections and New Equis Polling_October.pdf, Equis_2025 Elections and New Equis Polling_October.pdf

1. _ # Equis Pulsecheck Wave 2: Frequencies, October 15-29, 2025  # Q.9  I know it's a long way off, but if the November 2026 election for U.S. Congress were held today, for whom would you vote - the Demo_
2. _ # Equis Pulsecheck Wave 2: Frequencies, October 15-29, 2025  # Q.9  I know it's a long way off, but if the November 2026 election for U.S. Congress were held today, for whom would you vote - the Demo_
3. _ VeraAcTION 6 # Overview of the Ad Test  • Virginia is an excellent off-year bellwether, and in the 2023 cycle, the GOP spent over $25 million on ads there attacking Democrats as "soft on crime."  • R_
4. _ # EQUIS RESEARCH  # Methodology Note:  Survey conducted 10/15 – 10/29 via phones and text-to-web with 2000 registered voters who identify as Hispanic or Latino nationally. The sample included an over_
5. _# Methodology Note:  Survey conducted 10/15 – 10/29 via phones and text-to-web with 2000 registered voters who identify as Hispanic or Latino nationally. The sample included an oversample in the follo_

**Completion** (1.25s)  

The provided context does not contain specific information about the win number for Virginia's 7th Congressional District in the 2026 election. To determine the win number, one would typically need data on voter registration, historical turnout rates, and demographic trends specific to that district, none of which are included in the context.

---

## ChangeAgent

ChangeAgent: pending API integration

_This section will be populated automatically once ChangeAgent is registered via `register_custom_provider()` in llm_config.py._

---

## Timing Summary

| Provider | Query | Retrieval | Completion | Total |
|----------|-------|-----------|------------|-------|
| anthropic    | canvassing_cost      | 3.76s    | 3.17s      | 6.93s |
| anthropic    | win_number           | 3.65s    | 3.77s      | 7.42s |
| anthropic    | young_voters         | 3.48s    | 4.74s      | 8.22s |
| gemini       | canvassing_cost      | 2.66s    | 4.24s      | 6.90s |
| gemini       | win_number           | 1.27s    | 16.92s     | 18.19s |
| gemini       | young_voters         | 2.67s    | 4.82s      | 7.49s |
| openai       | canvassing_cost      | 3.92s    | 1.38s      | 5.30s |
| openai       | win_number           | 3.65s    | 1.25s      | 4.90s |
| openai       | young_voters         | 3.82s    | 2.26s      | 6.08s |
