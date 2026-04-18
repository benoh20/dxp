# Powerbuilder LLM Provider Comparison Report

**Generated:** 2026-04-18 10:25:35  
**Providers tested:** anthropic, cohere, gemini, groq, llama, mistral, openai  
**Queries:** 3  

---

# RAG Retrieval Comparison

Each provider retrieves context from its own Pinecone index using its native embedding model (anthropic and groq fall back to OpenAI embeddings), then answers via a single prompt — no tool calls or multi-agent pipeline.

---

## Anthropic

| Field | Value |
|-------|-------|
| Completion model | `claude-sonnet-4-5` |
| Embedding model  | `openai (fallback)` |
| Pinecone index   | `powerbuilder-anthropic` |

### Q1: Young voter targeting + messaging

> *I want to reach young voters in Virginia's 7th Congressional District. What precincts should I target and what message should I deliver?*

**Retrieval** (2.54s)  
Sources: HIT_Countering Racialized Politics About Crime in 2024.pdf, 2025-Civic-Power-Report-1.pdf, HIT_Countering Racialized Politics About Crime in 2024.pdf, HIT_Headcount_Public-Memo.pdf, HIT_Headcount_Public-Memo.pdf

1. _ VeraAcTION 6 # Overview of the Ad Test  • Virginia is an excellent off-year bellwether, and in the 2023 cycle, the GOP spent over $25 million on ads there attacking Democrats as "soft on crime."  • R_
2. _ # Targeting  In comparison to other programs, the state-based groups in this study targeted voter universes that were more racially diverse, younger, more geographically diverse, and included a large_
3. _ ©HITstrategies                            VeraAcTION  # Future Research Recommendations:  - Understanding how this messaging tests with voters across battleground states. - Finding more clarity on vo_
4. _ HITstrategies HEADCOUNT  # Young registered voters aged 18-34 exhibit different voting behavior based on their top issue and their media sources.  TO: Interested Parties  FROM: HIT Strategies, HeadCo_
5. _ HITstrategies HEADCOUNT  # Young registered voters aged 18-34 exhibit different voting behavior based on their top issue and their media sources.  TO: Interested Parties  FROM: HIT Strategies, HeadCo_

**Completion** (5.40s)  

Based on the provided research context, I cannot answer your specific question about which precincts to target in Virginia's 7th Congressional District, as the documents do not contain precinct-level data for that district.

However, regarding messaging for young voters, the research indicates you should focus on convincing them "of their vote's power to make change on the issues that matter most to them," as young voters (18-34) are "not a monolith" and vary significantly by gender, race, and media sources. On crime-related messaging specifically, the Virginia research suggests that a comprehensive "serious about safety" platform focusing on crime prevention performs well, rather than simply touting law enforcement credentials.

### Q2: Canvassing cost estimate

> *How much would it cost to run a canvassing program in Virginia's 7th Congressional District in 2026?*

**Retrieval** (2.54s)  
Sources: 876-Working-America-2025-Canvass-Downstream-Meta-Analysis-FINAL-4-1.pdf, HIT_Countering Racialized Politics About Crime in 2024.pdf, Equis_2025 Elections and New Equis Polling_October.pdf, Equis_2025 Elections and New Equis Polling_October.pdf, Equis_2025 Elections and New Equis Polling_October.pdf

1. _  # Impact of Canvassing  - Analyst Institute’s 2024 GOTV meta-analysis of 24 canvassing treatments reaching over 8 million voters found that canvassing programs had inconsistent same-cycle effects on_
2. _ VeraAcTION 6 # Overview of the Ad Test  • Virginia is an excellent off-year bellwether, and in the 2023 cycle, the GOP spent over $25 million on ads there attacking Democrats as "soft on crime."  • R_
3. _ # Equis Pulsecheck Wave 2: Frequencies, October 15-29, 2025  # Q.9  I know it's a long way off, but if the November 2026 election for U.S. Congress were held today, for whom would you vote - the Demo_
4. _ # Equis Pulsecheck Wave 2: Frequencies, October 15-29, 2025  # Q.9  I know it's a long way off, but if the November 2026 election for U.S. Congress were held today, for whom would you vote - the Demo_
5. _ # Equis Pulsecheck Wave 2: Frequencies, October 15-29, 2025  # Q.9  I know it's a long way off, but if the November 2026 election for U.S. Congress were held today, for whom would you vote - the Demo_

**Completion** (3.15s)  

Based on the research context provided, I cannot answer this question. The documents include information about the effectiveness of canvassing programs and polling data, but they do not contain any cost estimates or budget information for running canvassing operations in Virginia's 7th Congressional District or any other specific location.

### Q3: Win number

> *What is the win number for Virginia's 7th Congressional District in 2026?*

**Retrieval** (2.54s)  
Sources: Equis_2025 Elections and New Equis Polling_October.pdf, Equis_2025 Elections and New Equis Polling_October.pdf, Equis_2025 Elections and New Equis Polling_October.pdf, HIT_Countering Racialized Politics About Crime in 2024.pdf, 876-Working-America-2025-Canvass-Downstream-Meta-Analysis-FINAL-4-1.pdf

1. _ # Equis Pulsecheck Wave 2: Frequencies, October 15-29, 2025  # Q.9  I know it's a long way off, but if the November 2026 election for U.S. Congress were held today, for whom would you vote - the Demo_
2. _ # Equis Pulsecheck Wave 2: Frequencies, October 15-29, 2025  # Q.9  I know it's a long way off, but if the November 2026 election for U.S. Congress were held today, for whom would you vote - the Demo_
3. _ # Equis Pulsecheck Wave 2: Frequencies, October 15-29, 2025  # Q.9  I know it's a long way off, but if the November 2026 election for U.S. Congress were held today, for whom would you vote - the Demo_
4. _ VeraAcTION 6 # Overview of the Ad Test  • Virginia is an excellent off-year bellwether, and in the 2023 cycle, the GOP spent over $25 million on ads there attacking Democrats as "soft on crime."  • R_
5. _ # Non-Midterm Same-cycle ITT Details  | State     | Total N | ITT   | SE   | P-value | Lower 90% CI | Higher 90% CI | Control Turnout | | --------- | ------- | ----- | ---- | ------- | ------------ |_

**Completion** (3.40s)  

I cannot answer this question based on the provided research context. The documents include polling data about the 2026 Congressional elections and information about Virginia political campaigns, but none of them contain specific information about the win number (the number of votes needed to win) for Virginia's 7th Congressional District in 2026.

---

## Cohere

| Field | Value |
|-------|-------|
| Completion model | `command-r-plus` |
| Embedding model  | `embed-english-v3.0` |
| Pinecone index   | `powerbuilder-cohere` |

### Q1: Young voter targeting + messaging

> *I want to reach young voters in Virginia's 7th Congressional District. What precincts should I target and what message should I deliver?*

**Error:** `Completion failed: headers: {'access-control-expose-headers': 'X-Debug-Trace-ID', 'cache-control': 'no-cache, no-store, no-transform, must-revalidate, private, max-age=0', 'content-encoding': 'gzip', 'content-type': 'application/json', 'expires': 'Thu, 01 Jan 1970 00:00:00 GMT', 'pragma': 'no-cache', 'vary': 'Origin,Accept-Encoding', 'x-accel-expires': '0', 'x-debug-trace-id': 'a7b12627dfda157e57d86814e83eeef3', 'x-endpoint-monthly-call-limit': '1000', 'x-trial-endpoint-call-limit': '20', 'x-trial-endpoint-call-remaining': '19', 'date': 'Sat, 18 Apr 2026 14:16:10 GMT', 'x-envoy-upstream-service-time': '3', 'server': 'envoy', 'via': '1.1 google', 'alt-svc': 'h3=":443"; ma=2592000', 'transfer-encoding': 'chunked'}, status_code: 404, body: {'id': '6b8df515-cc3e-4f4d-9da0-34276743d602', 'message': "model 'command-r-plus' was removed on September 15, 2025. See https://docs.cohere.com/docs/models#command for a list of models you can use instead."}`

### Q2: Canvassing cost estimate

> *How much would it cost to run a canvassing program in Virginia's 7th Congressional District in 2026?*

**Error:** `Completion failed: headers: {'access-control-expose-headers': 'X-Debug-Trace-ID', 'cache-control': 'no-cache, no-store, no-transform, must-revalidate, private, max-age=0', 'content-encoding': 'gzip', 'content-type': 'application/json', 'expires': 'Thu, 01 Jan 1970 00:00:00 GMT', 'pragma': 'no-cache', 'vary': 'Origin,Accept-Encoding', 'x-accel-expires': '0', 'x-debug-trace-id': 'ca24ae83f91086019cadde4f3427ea27', 'x-endpoint-monthly-call-limit': '1000', 'x-trial-endpoint-call-limit': '20', 'x-trial-endpoint-call-remaining': '17', 'date': 'Sat, 18 Apr 2026 14:16:10 GMT', 'x-envoy-upstream-service-time': '7', 'server': 'envoy', 'via': '1.1 google', 'alt-svc': 'h3=":443"; ma=2592000,h3-29=":443"; ma=2592000', 'transfer-encoding': 'chunked'}, status_code: 404, body: {'id': 'cf1afc19-ed4b-426a-b647-98a0d94e3f49', 'message': "model 'command-r-plus' was removed on September 15, 2025. See https://docs.cohere.com/docs/models#command for a list of models you can use instead."}`

### Q3: Win number

> *What is the win number for Virginia's 7th Congressional District in 2026?*

**Error:** `Completion failed: headers: {'access-control-expose-headers': 'X-Debug-Trace-ID', 'cache-control': 'no-cache, no-store, no-transform, must-revalidate, private, max-age=0', 'content-encoding': 'gzip', 'content-type': 'application/json', 'expires': 'Thu, 01 Jan 1970 00:00:00 GMT', 'pragma': 'no-cache', 'vary': 'Origin,Accept-Encoding', 'x-accel-expires': '0', 'x-debug-trace-id': '60ce1a7286aa05ed03f0192d34e3ecea', 'x-endpoint-monthly-call-limit': '1000', 'x-trial-endpoint-call-limit': '20', 'x-trial-endpoint-call-remaining': '18', 'date': 'Sat, 18 Apr 2026 14:16:10 GMT', 'x-envoy-upstream-service-time': '3', 'server': 'envoy', 'via': '1.1 google', 'alt-svc': 'h3=":443"; ma=2592000,h3-29=":443"; ma=2592000', 'transfer-encoding': 'chunked'}, status_code: 404, body: {'id': 'abba333e-ec1b-4bd9-9553-68fe3d23a47e', 'message': "model 'command-r-plus' was removed on September 15, 2025. See https://docs.cohere.com/docs/models#command for a list of models you can use instead."}`

---

## Gemini

| Field | Value |
|-------|-------|
| Completion model | `gemini-2.5-flash` |
| Embedding model  | `models/gemini-embedding-001` |
| Pinecone index   | `research-index` |

### Q1: Young voter targeting + messaging

> *I want to reach young voters in Virginia's 7th Congressional District. What precincts should I target and what message should I deliver?*

**Retrieval** (2.10s)  
Sources: 25 Things We Learned about Young Voters in 2025 _ CIRCLE.pdf, HIT_Headcount_Public-Memo.pdf, HIT_Headcount_Public-Memo.pdf, 25 Things We Learned about Young Voters in 2025 _ CIRCLE.pdf, 25 Things We Learned about Young Voters in 2025 _ CIRCLE.pdf

1. _ 25 Things We Learned about Young Voters in 2025 | CIRCLE  The vote choice of young voters (ages 18-29) in the 2025 New York City mayoral election.  |              | Mamdani | Cuomo | Sliwa | | ------_
2. _ HEADCOUNT  # Survey Methodology:  These findings are from a proprietary survey conducted by HIT Strategies and HeadCount. This survey consisted of 1000 registered voters ages 18-35 nationwide. The su_
3. _ HEADCOUNT  # Survey Methodology:  These findings are from a proprietary survey conducted by HIT Strategies and HeadCount. This survey consisted of 1000 registered voters ages 18-35 nationwide. The su_
4. _ 4/18/26, 8:10 AM # 25 Things We Learned about Young Voters in 2025  # CIRCLE  Youth Trust Peers, Nonprofits, and Local Government; Distrust Social Media Companies and the Republican Party  Institutio_
5. _  # 25 Things We Learned about Young Voters in 2025  There Is a Strong Link Between In-Person Interactions and Voting  The self-reported frequency with which young people, ages 18-34, report that they_

**Completion** (7.76s)  

Based solely on the provided context, specific precincts for Virginia's 7th Congressional District cannot be identified, as the research does not contain district-specific data. To effectively reach young voters (ages 18-34), the message should be delivered through trusted local channels, emphasizing community engagement. Young people demonstrate significant trust in their peers, neighbors, and local government. Furthermore, there is a strong correlation between in-person community interactions and higher voter participation among this demographic, suggesting a ground-level, relational approach is key.

### Q2: Canvassing cost estimate

> *How much would it cost to run a canvassing program in Virginia's 7th Congressional District in 2026?*

**Retrieval** (2.08s)  
Sources: 876-Working-America-2025-Canvass-Downstream-Meta-Analysis-FINAL-4-1.pdf, 876-Working-America-2025-Canvass-Downstream-Meta-Analysis-FINAL-4-1.pdf, 876-Working-America-2025-Canvass-Downstream-Meta-Analysis-FINAL-4-1.pdf, 876-Working-America-2025-Canvass-Downstream-Meta-Analysis-FINAL-4-1.pdf, 876-Working-America-2025-Canvass-Downstream-Meta-Analysis-FINAL-4-1.pdf

1. _ # Preview of Findings  - Working America’s canvassing programs increased same-cycle voter turnout in most but not all elections between 2014 and 2022. - Earlier programs had more reliable downstream _
2. _ # Canvassing in Context  - Analyst Institute’s meta-analysis finds that canvassing effects vary widely, likely because implementation differs more across programs than more standardized modes like ma_
3. _ # Interpreting Mixed Results  - In contrast to 2014 and 2018, 2022 programs had neither same-cycle nor downstream effects on average, whether or not contact was successful. - The lack of same-cycle a_
4. _  # Impact of Canvassing  - Analyst Institute’s 2024 GOTV meta-analysis of 24 canvassing treatments reaching over 8 million voters found that canvassing programs had inconsistent same-cycle effects on_
5. _  # Canvassing Conversations  - Working America trains their mostly local paid canvassers to hold open-ended conversations rather than memorizing scripts. - Their conversations include both persuasion_

**Completion** (2.13s)  

The provided research context does not contain any information regarding the cost of running a canvassing program. The documents focus on the effectiveness, consistency, targeting strategies, and conversational approaches of Working America's canvassing programs. There are no financial figures, budget details, or cost-estimation methodologies included in the provided text. Therefore, it is not possible to determine the cost of a canvassing program in Virginia's 7th Congressional District in 2026 based solely on this context.

### Q3: Win number

> *What is the win number for Virginia's 7th Congressional District in 2026?*

**Retrieval** (0.72s)  
Sources: Equis_2025 Elections and New Equis Polling_October.pdf, Equis_2025 Elections and New Equis Polling_October.pdf, Equis_2025 Elections and New Equis Polling_October.pdf, 2025-Civic-Power-Report-1.pdf, HIT_Countering Racialized Politics About Crime in 2024.pdf

1. _ # Equis Pulsecheck Wave 2: Frequencies, October 15-29, 2025  # Q.9  I know it's a long way off, but if the November 2026 election for U.S. Congress were held today, for whom would you vote - the Demo_
2. _ # Equis Pulsecheck Wave 2: Frequencies, October 15-29, 2025  # Q.9  I know it's a long way off, but if the November 2026 election for U.S. Congress were held today, for whom would you vote - the Demo_
3. _ # Equis Pulsecheck Wave 2: Frequencies, October 15-29, 2025  # Q.9  I know it's a long way off, but if the November 2026 election for U.S. Congress were held today, for whom would you vote - the Demo_
4. _ # THE 2024 ELECTION: WHAT HAPPENED?  Donald Trump won in 2024 with a larger and more racially diverse coalition than he had in 2020. Kamala Harris saw a drop-off in Democratic voter turnout and suppo_
5. _  # Methodology  # VeraActiOn 5  | Universe        | Sample Size        | Methodology                                                                                                                   _

**Completion** (10.86s)  

The provided research context does not contain specific polling data or election analysis for Virginia's 7th Congressional District in 2026. While Equis Pulsecheck Wave 2 provides general sentiment for the 2026 U.S. Congress election, showing 51% total Democratic support and 36% total Republican support, this is not disaggregated by specific districts. Therefore, a precise "win number" for Virginia's 7th Congressional District cannot be determined from the given information.

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

**Retrieval** (2.82s)  
Sources: HIT_Countering Racialized Politics About Crime in 2024.pdf, 2025-Civic-Power-Report-1.pdf, HIT_Countering Racialized Politics About Crime in 2024.pdf, HIT_Headcount_Public-Memo.pdf, HIT_Headcount_Public-Memo.pdf

1. _ VeraAcTION 6 # Overview of the Ad Test  • Virginia is an excellent off-year bellwether, and in the 2023 cycle, the GOP spent over $25 million on ads there attacking Democrats as "soft on crime."  • R_
2. _ # Targeting  In comparison to other programs, the state-based groups in this study targeted voter universes that were more racially diverse, younger, more geographically diverse, and included a large_
3. _ ©HITstrategies                            VeraAcTION  # Future Research Recommendations:  - Understanding how this messaging tests with voters across battleground states. - Finding more clarity on vo_
4. _ HITstrategies HEADCOUNT  # Young registered voters aged 18-34 exhibit different voting behavior based on their top issue and their media sources.  TO: Interested Parties  FROM: HIT Strategies, HeadCo_
5. _ HITstrategies HEADCOUNT  # Young registered voters aged 18-34 exhibit different voting behavior based on their top issue and their media sources.  TO: Interested Parties  FROM: HIT Strategies, HeadCo_

**Completion** (1.64s)  

To effectively reach young voters in Virginia's 7th Congressional District, focus on precincts with a high concentration of racially diverse, younger, and low-propensity voters, as these groups have shown high modeled progressivity support scores. Tailor your message to emphasize the power of their vote in driving change on issues that matter most to them, particularly around public safety and crime prevention. Highlight a comprehensive "serious about safety" platform that balances crime prevention with addressing immediate fears, as this approach has resonated well in ad tests.

### Q2: Canvassing cost estimate

> *How much would it cost to run a canvassing program in Virginia's 7th Congressional District in 2026?*

**Retrieval** (2.53s)  
Sources: 876-Working-America-2025-Canvass-Downstream-Meta-Analysis-FINAL-4-1.pdf, HIT_Countering Racialized Politics About Crime in 2024.pdf, Equis_2025 Elections and New Equis Polling_October.pdf, Equis_2025 Elections and New Equis Polling_October.pdf, Equis_2025 Elections and New Equis Polling_October.pdf

1. _  # Impact of Canvassing  - Analyst Institute’s 2024 GOTV meta-analysis of 24 canvassing treatments reaching over 8 million voters found that canvassing programs had inconsistent same-cycle effects on_
2. _ VeraAcTION 6 # Overview of the Ad Test  • Virginia is an excellent off-year bellwether, and in the 2023 cycle, the GOP spent over $25 million on ads there attacking Democrats as "soft on crime."  • R_
3. _ # Equis Pulsecheck Wave 2: Frequencies, October 15-29, 2025  # Q.9  I know it's a long way off, but if the November 2026 election for U.S. Congress were held today, for whom would you vote - the Demo_
4. _ # Equis Pulsecheck Wave 2: Frequencies, October 15-29, 2025  # Q.9  I know it's a long way off, but if the November 2026 election for U.S. Congress were held today, for whom would you vote - the Demo_
5. _ # Equis Pulsecheck Wave 2: Frequencies, October 15-29, 2025  # Q.9  I know it's a long way off, but if the November 2026 election for U.S. Congress were held today, for whom would you vote - the Demo_

**Completion** (1.34s)  

The provided context does not include specific information on the costs associated with running a canvassing program in Virginia's 7th Congressional District in 2026. To estimate the cost, one would typically need to consider factors such as the number of voters to be reached, the duration of the canvassing effort, staffing and training expenses, materials, and logistical support. Historical data from similar past programs or consulting with organizations experienced in political canvassing could provide a more accurate estimate.

### Q3: Win number

> *What is the win number for Virginia's 7th Congressional District in 2026?*

**Retrieval** (3.90s)  
Sources: Equis_2025 Elections and New Equis Polling_October.pdf, Equis_2025 Elections and New Equis Polling_October.pdf, Equis_2025 Elections and New Equis Polling_October.pdf, HIT_Countering Racialized Politics About Crime in 2024.pdf, 876-Working-America-2025-Canvass-Downstream-Meta-Analysis-FINAL-4-1.pdf

1. _ # Equis Pulsecheck Wave 2: Frequencies, October 15-29, 2025  # Q.9  I know it's a long way off, but if the November 2026 election for U.S. Congress were held today, for whom would you vote - the Demo_
2. _ # Equis Pulsecheck Wave 2: Frequencies, October 15-29, 2025  # Q.9  I know it's a long way off, but if the November 2026 election for U.S. Congress were held today, for whom would you vote - the Demo_
3. _ # Equis Pulsecheck Wave 2: Frequencies, October 15-29, 2025  # Q.9  I know it's a long way off, but if the November 2026 election for U.S. Congress were held today, for whom would you vote - the Demo_
4. _ VeraAcTION 6 # Overview of the Ad Test  • Virginia is an excellent off-year bellwether, and in the 2023 cycle, the GOP spent over $25 million on ads there attacking Democrats as "soft on crime."  • R_
5. _ # Non-Midterm Same-cycle ITT Details  | State     | Total N | ITT   | SE   | P-value | Lower 90% CI | Higher 90% CI | Control Turnout | | --------- | ------- | ----- | ---- | ------- | ------------ |_

**Completion** (1.29s)  

Based on the provided context, the specific win number for Virginia's 7th Congressional District in 2026 is not directly available. However, the polling data indicates a general preference for Democratic candidates, with 51% of respondents leaning Democratic compared to 36% leaning Republican. This suggests that a Democratic candidate may have a favorable chance in districts with similar dynamics, but the exact win number would require more localized data and analysis specific to Virginia's 7th District.

---

## RAG Timing Summary

| Provider | Query | Retrieval | Completion | Total |
|----------|-------|-----------|------------|-------|
| anthropic    | canvassing_cost      | 2.54s    | 3.15s      | 5.69s |
| anthropic    | win_number           | 2.54s    | 3.40s      | 5.94s |
| anthropic    | young_voters         | 2.54s    | 5.40s      | 7.94s |
| gemini       | canvassing_cost      | 2.08s    | 2.13s      | 4.21s |
| gemini       | win_number           | 0.72s    | 10.86s     | 11.58s |
| gemini       | young_voters         | 2.10s    | 7.76s      | 9.86s |
| openai       | canvassing_cost      | 2.53s    | 1.34s      | 3.87s |
| openai       | win_number           | 3.90s    | 1.29s      | 5.19s |
| openai       | young_voters         | 2.82s    | 1.64s      | 4.46s |

---

# Full Pipeline Comparison

Each provider runs the complete LangGraph pipeline via `run_query()`: researcher → election_results → win_number → precincts → messaging → cost_calculator → synthesizer. Includes live API calls (Census CVAP, MEDSL election results, FEC data). Census/FEC/MEDSL failures are non-fatal.

---

## Anthropic

| Field | Value |
|-------|-------|
| Completion model | `claude-sonnet-4-5` |

### Q1: Young voter targeting + messaging

> *I want to reach young voters in Virginia's 7th Congressional District. What precincts should I target and what message should I deliver?*

**Pipeline time:** 42.59s  
**Agents called:** researcher, election_results, win_number, precincts, messaging, cost_calculator  
**Non-fatal errors (1):** ElectionAnalyst: MEDSL party-level data unavailable — margin trend and D/R vote shares cannot be computed. Turnout data from master CSV will still be used.

**Final Answer:**

# Program Briefing: Targeting Young Voters in Virginia's 7th Congressional District

## Target Precincts
To effectively reach young voters in Virginia's 7th Congressional District, we should focus on precincts with high concentrations of voters aged 18-34. The following precincts have been identified as having the highest youth voting-age population (VAP):

- **Trevvett** (Youth VAP: 1,942.73)
- **Tucker** (Youth VAP: 1,914.09)
- **Drewrys Bluff** (Youth VAP: 1,826.16)
- **Five Forks** (Youth VAP: 1,749.47)
- **Azalea** (Youth VAP: 1,703.58)
- **Hermitage** (Youth VAP: 1,647.49)
- **Longan** (Youth VAP: 1,553.87)
- **Chippenham** (Youth VAP: 1,465.20)
- **John J. Wright** (Youth VAP: 1,456.81)
- **Clover Hill** (Youth VAP: 1,295.04)

These precincts should be prioritized for outreach efforts to maximize engagement with young voters.

## Messaging Strategy
Our messaging should focus on empowering young voters to influence change on issues that matter most to them, particularly safety and media trust. The following key points should guide our communication:

- **Empowerment:** Highlight the power of young voters to make a difference in shaping the future.
- **Safety:** Emphasize a comprehensive approach to safety that includes prevention, crisis response, and violence reduction. This message resonates well with young and diverse voters.
- **Media Trust:** Encourage voters to rely on trustworthy media sources for informed decision-making.

### Media Consumption Insights
- **Young Men:** More likely to trust podcasts, Twitter/X, and YouTube for political news.
- **Young Women:** Prefer TikTok, national and local TV news stations, and informational articles online.

### Messaging Channels
- **Digital Ads:** Use platforms like Facebook and Instagram to reach young voters with targeted ads emphasizing safety and empowerment.
- **Canvassing and Phone Banking:** Engage directly with voters using a script that highlights the candidate's stance on safety and media trust.
- **Text Messaging:** Send concise, personalized messages to remind voters of the importance of their participation and the candidate's platform.

### Key Message: "Empower young voters to influence change on issues that matter to them."

## Budget Considerations
Based on historical spending data, the estimated budget for a comprehensive outreach program in this district is approximately $1,341,459. This includes allocations for personnel, mail, digital, phone, and miscellaneous expenses.

- **Personnel:** $469,511
- **Mail:** $268,292
- **Digital:** $335,365
- **Phones:** $134,146
- **Miscellaneous:** $134,146

*Research sourced from materials dated as recently as 2022.*

### Q2: Canvassing cost estimate

> *How much would it cost to run a canvassing program in Virginia's 7th Congressional District in 2026?*

**Pipeline time:** 36.39s  
**Agents called:** researcher, election_results, win_number, precincts, messaging, cost_calculator  
**Non-fatal errors (1):** ElectionAnalyst: MEDSL party-level data unavailable — margin trend and D/R vote shares cannot be computed. Turnout data from master CSV will still be used.

**Final Answer:**

# Program Briefing: Canvassing Program Cost in Virginia's 7th Congressional District for 2026

## Overview

Our campaign is considering a comprehensive canvassing program in Virginia's 7th Congressional District for the 2026 election cycle. This briefing outlines the estimated costs and strategic considerations based on historical data and recent research findings.

## Estimated Costs

Based on historical spending and industry averages for Congressional races, the estimated cost to run a canvassing program in Virginia's 7th Congressional District is detailed below:

- **Total Estimated Cost:** $1,341,459
  - **Personnel:** $469,511
  - **Mail:** $268,292
  - **Digital:** $335,365
  - **Phones:** $134,146
  - **Miscellaneous:** $134,146

### Per-Contact Rates

- **Door Knock:** $7.00 per door (8 doors/hour average)
- **Phone Call:** $1.50 per call
- **Text Message:** $0.05 per text
- **Mail Piece:** $1.00 per piece + $500 flat design fee
- **Digital:** $0.02 per impression ($1,000 minimum per flight)

## Strategic Considerations

- **Target Demographic:** Voters with inconsistent voting history, with a focus on young and Black voters who resonate with a "serious about safety" platform.
- **Messaging:** Emphasize a comprehensive approach to community safety, including crime prevention, crisis response, and violence prevention.
- **Competitiveness:** The district is rated as Lean Democratic with a Cook PVI of D+6, indicating a favorable environment for our candidate.

## Research Findings

- **Impact of Canvassing:** Previous analyses have shown that canvassing can have both immediate and downstream positive effects on voter turnout, particularly among voters with inconsistent voting histories.
- **Ad Performance:** Messaging around a comprehensive "serious about safety" platform has been effective, especially among Black and young voters, outperforming traditional "tough on crime" narratives.

*Research sourced from materials dated as recently as 2022.*

### Q3: Win number

> *What is the win number for Virginia's 7th Congressional District in 2026?*

**Pipeline time:** 4.90s  
**Agents called:** win_number  

**Final Answer:**

# Virginia's 7th Congressional District: 2026 Win Number Briefing

## Overview

In preparation for the 2026 election cycle, our campaign has focused on understanding the key metrics necessary to secure a victory in Virginia's 7th Congressional District. This briefing outlines the win number, projected turnout, and relevant historical context.

## Key Metrics

- **Win Number**: To secure a win in Virginia's 7th Congressional District in 2026, our campaign needs to achieve a minimum of **150,404 votes**.
- **Projected Turnout**: The anticipated voter turnout for the district is approximately **289,239**.
- **Voter Universe**: The total citizen voting age population (CVAP) in the district is estimated at **542,664**.

## Historical Context

- **Average Turnout Percentage**: Historically, the average voter turnout percentage for the district is **53.3%**.
- **Victory Margin**: The victory margin is projected at **0.52%**, indicating a highly competitive race.
- **Averaged Election Cycles**: The projections are based on data from past midterm election cycles, specifically the years **2014, 2018, and 2022**.

## Strategic Implications

- Given the narrow victory margin and competitive nature of the district, our campaign must focus on maximizing voter engagement and turnout efforts.
- Targeted outreach and strategic allocation of resources will be crucial to surpass the win number and secure a victory.

*Research sourced from materials dated as recently as unknown.*

---

## Cohere

| Field | Value |
|-------|-------|
| Completion model | `command-r-plus` |

### Q1: Young voter targeting + messaging

> *I want to reach young voters in Virginia's 7th Congressional District. What precincts should I target and what message should I deliver?*

**Pipeline time:** 35.98s  
**Agents called:** researcher, election_results, win_number, precincts, messaging, cost_calculator  
**Non-fatal errors (1):** ElectionAnalyst: MEDSL party-level data unavailable — margin trend and D/R vote shares cannot be computed. Turnout data from master CSV will still be used.

**Final Answer:**

# Program Briefing: Engaging Young Voters in Virginia's 7th Congressional District

## Target Precincts

To effectively reach young voters in Virginia's 7th Congressional District, we should focus on precincts with high concentrations of voters aged 18-34. The following precincts have been identified as priorities based on their youth voter population:

- **Trevvett (Precinct Geoid: 51087-111-Maude Trevvett)**
- **Tucker (Precinct Geoid: 51087-315-Tucker)**
- **Drewrys Bluff (Precinct Geoid: 51041-105-DrewrysBluff)**
- **Five Forks (Precinct Geoid: 51041-210-FiveForks)**
- **Azalea (Precinct Geoid: 51087-201-Azalea)**
- **Hermitage (Precinct Geoid: 51087-105-Hermitage)**
- **Longan (Precinct Geoid: 51087-110-Longan)**
- **Chippenham (Precinct Geoid: 51041-207-Chippenham)**
- **John J. Wright (Precinct Geoid: 51177-103 - JOHN J. WRIGHT)**
- **Clover Hill (Precinct Geoid: 51041-412-CloverHill)**

These precincts have been selected due to their significant youth voter population, which provides an opportunity to engage and mobilize young voters effectively.

## Messaging Strategy

Our messaging should focus on empowering young voters and addressing issues that resonate with them. Based on recent findings, the following key messages should be delivered:

- **Empowerment and Change:** Emphasize the power of young voters to create meaningful change on issues that matter to them. Highlight the importance of their participation in shaping the future.
  
- **Public Safety:** Communicate Candidate X's commitment to a comprehensive 'serious about safety' platform. This approach focuses on preventing crime and responding effectively to crises, resonating strongly with young voters.

- **Media Consumption:** Tailor messages to align with the media consumption habits of young voters. Use platforms like TikTok, national TV news, and online articles for young women, and podcasts, Twitter/X, and YouTube for young men.

- **Vote Power:** Reinforce the message that their vote is crucial in making a difference, especially on issues like public safety, which are top concerns in the district.

## Communication Channels

To effectively reach young voters, we should utilize a mix of communication channels:

- **Digital Advertising:** Use platforms like Facebook, Instagram, and display ads to reach young voters where they spend their time online. A/B test different ad variations to optimize engagement.

- **Peer-to-Peer Texting:** Engage young voters directly through personalized SMS outreach, ensuring messages are concise and include an opt-out option.

- **Door-to-Door Canvassing:** Conduct face-to-face interactions in targeted precincts, emphasizing the importance of their vote and addressing any concerns they may have.

- **Phone Banking:** Reach out to young voters through phone calls, providing information on Candidate X's platform and encouraging them to make a voting plan.

By focusing on these targeted precincts and delivering a message that resonates with young voters, we can effectively engage and mobilize this critical demographic in Virginia's 7th Congressional District.

*Research sourced from materials dated as recently as 2022.*

### Q2: Canvassing cost estimate

> *How much would it cost to run a canvassing program in Virginia's 7th Congressional District in 2026?*

**Pipeline time:** 39.10s  
**Agents called:** researcher, election_results, win_number, precincts, messaging, cost_calculator  
**Non-fatal errors (1):** ElectionAnalyst: MEDSL party-level data unavailable — margin trend and D/R vote shares cannot be computed. Turnout data from master CSV will still be used.

**Final Answer:**

# Program Briefing: Canvassing Program Cost in Virginia's 7th Congressional District for 2026

## Overview

Our campaign is evaluating the costs associated with running a canvassing program in Virginia's 7th Congressional District for the 2026 election cycle. This briefing synthesizes the latest research findings and cost estimates to provide a comprehensive understanding of the financial requirements.

## Key Findings

- **Historical Spending**: The average total campaign disbursement for similar races in the district was approximately **$1,341,459**. This figure is based on data from 21 candidates across two comparable election cycles (2018 and 2022).

- **Projected Turnout**: The projected voter turnout for 2026 is estimated at **289,239** with a win number of **150,404** votes needed for victory.

- **Cost Estimates by Category**:
  - **Personnel**: $469,511
  - **Mail**: $268,292
  - **Digital**: $335,365
  - **Phones**: $134,146
  - **Miscellaneous**: $134,146

## Canvassing Program Specifics

- **Door Knocking**: 
  - **Cost per Door**: $7.00
  - **Average Doors per Hour**: 8

- **Phone Calls**: 
  - **Cost per Call**: $1.50

- **Text Messaging**: 
  - **Cost per Text**: $0.05

- **Mail**: 
  - **Cost per Piece**: $1.00
  - **Design Fee**: $500 flat fee

- **Digital Advertising**: 
  - **Cost per Impression**: $0.02
  - **Minimum Spend per Flight**: $1,000

## Strategic Considerations

- **Target Demographic**: Focus on voters with inconsistent voting histories, as canvassing has shown positive effects on turnout among this group.
  
- **Messaging**: Emphasize a comprehensive "serious about safety" platform, which has resonated well with Black voters and young voters in previous cycles.

- **Precincts**: There are 295 precincts in the district, with a focus on those with the highest total voting-age population for maximum impact.

## Conclusion

The estimated cost to run a comprehensive canvassing program in Virginia's 7th Congressional District for the 2026 election cycle is aligned with historical spending patterns, with a total budget of approximately **$1,341,459**. This includes personnel, mail, digital, phone, and miscellaneous expenses. Our strategy will focus on engaging voters with inconsistent voting histories and leveraging effective messaging to maximize turnout.

*Research sourced from materials dated as recently as 2022.*

### Q3: Win number

> *What is the win number for Virginia's 7th Congressional District in 2026?*

**Pipeline time:** 6.57s  
**Agents called:** win_number  

**Final Answer:**

# Virginia's 7th Congressional District Win Number for 2026

## Overview

In preparation for the 2026 midterm elections, our campaign has analyzed the necessary win number for Virginia's 7th Congressional District. This analysis is crucial for strategizing our voter outreach and resource allocation effectively.

## Key Findings

- **Win Number**: The projected win number for Virginia's 7th Congressional District in 2026 is **150,404** votes.
- **Projected Turnout**: The expected voter turnout is **289,239**, based on historical data from previous midterm election cycles.
- **Voter Universe**: The total citizen voting-age population (CVAP) in the district is **542,664**.
- **Average Turnout Percentage**: The average turnout percentage for the district is approximately **53.3%**.
- **Victory Margin**: A narrow victory margin of **0.52%** is anticipated, emphasizing the importance of every vote.

## Historical Context

- The projections are based on an analysis of midterm election cycles from **2014, 2018, and 2022**.
- These historical cycles provide a reliable foundation for understanding voter behavior and turnout trends in the district.

## Strategic Implications

- **Resource Allocation**: Given the narrow victory margin, it is imperative to focus resources on maximizing voter engagement and turnout.
- **Voter Outreach**: Targeted outreach efforts should be intensified to ensure we meet or exceed the projected win number.
- **Data-Driven Decisions**: Continual monitoring of voter registration and engagement metrics will be crucial to adjust strategies as needed.

*Research sourced from materials dated as recently as unknown.*

---

## Gemini

| Field | Value |
|-------|-------|
| Completion model | `gemini-2.5-flash` |

### Q1: Young voter targeting + messaging

> *I want to reach young voters in Virginia's 7th Congressional District. What precincts should I target and what message should I deliver?*

**Pipeline time:** 42.06s  
**Agents called:** researcher, election_results, win_number, precincts, messaging, cost_calculator  
**Non-fatal errors (1):** ElectionAnalyst: MEDSL party-level data unavailable — margin trend and D/R vote shares cannot be computed. Turnout data from master CSV will still be used.

**Final Answer:**

# Program Briefing: Engaging Young Voters in Virginia's 7th Congressional District

## Target Precincts

To effectively reach young voters in Virginia's 7th Congressional District, we should focus on precincts with high concentrations of voters aged 18-34. Based on our analysis, the following precincts have the highest youth voter populations:

- **Trevvett**: Youth VAP 1,942.73
- **Tucker**: Youth VAP 1,914.09
- **Drewrys Bluff**: Youth VAP 1,826.16
- **Five Forks**: Youth VAP 1,749.47
- **Azalea**: Youth VAP 1,703.58
- **Hermitage**: Youth VAP 1,647.49
- **Longan**: Youth VAP 1,553.87
- **Chippenham**: Youth VAP 1,465.20
- **John J. Wright**: Youth VAP 1,456.81
- **Clover Hill**: Youth VAP 1,295.04

These precincts should be prioritized for outreach efforts to maximize impact among young voters.

## Messaging Strategy

### Key Message
Our campaign will focus on **empowering young voters to shape their future**. This message should highlight the importance of their participation in the electoral process and how their votes can drive change on critical issues.

### Issue Focus
- **Public Safety**: Emphasize a comprehensive "serious about safety" platform that resonates with young and diverse voters. This approach includes preventing crime, responding effectively to crises, and stopping violence. This message has shown strong resonance with young voters, particularly those aged 18-24.
  
### Media and Communication Channels
- **For Young Men**: Utilize podcasts, Twitter/X, and YouTube as these are trusted sources for political news among this demographic.
- **For Young Women**: Focus on TikTok, national and local TV news stations, and informational articles online.
  
### Canvassing and Outreach
- **Door-to-Door Canvassing**: Engage young voters with a script that emphasizes the power of their vote and the candidate's commitment to public safety and youth empowerment.
- **Phone Banking**: Use a concise script to gauge support and discuss key issues like public safety.
- **Text Messaging**: Send targeted SMS messages to remind young voters of the importance of their vote and provide information on voting logistics.
- **Digital Advertising**: Run ads on platforms like Facebook and Instagram with messages focused on public safety and the importance of voting.

### Addressing Common Objections
- **"My vote doesn't matter"**: Reinforce that young voters have the power to drive change on the issues that matter most to them.
- **"I'm not sure about safety policies"**: Highlight the candidate's commitment to a comprehensive safety plan that addresses real community needs.

*Research sourced from materials dated as recently as 2022.*

### Q2: Canvassing cost estimate

> *How much would it cost to run a canvassing program in Virginia's 7th Congressional District in 2026?*

**Pipeline time:** 42.66s  
**Agents called:** researcher, election_results, win_number, precincts, messaging, cost_calculator  
**Non-fatal errors (1):** ElectionAnalyst: MEDSL party-level data unavailable — margin trend and D/R vote shares cannot be computed. Turnout data from master CSV will still be used.

**Final Answer:**

# Program Briefing: Canvassing Program Cost in Virginia's 7th Congressional District for 2026

## Overview

Our campaign is considering the implementation of a canvassing program in Virginia's 7th Congressional District for the 2026 election cycle. This briefing outlines the estimated costs associated with such a program based on historical spending and industry averages.

## Historical Spending and Budget Estimates

- **Average Total Campaign Disbursement**: $1,341,459
  - This figure is based on data from 21 candidates across two comparable election cycles (2018 and 2022).

### Estimated Spending by Category

- **Personnel**: $469,511
- **Mail**: $268,292
- **Digital**: $335,365
- **Phones**: $134,146
- **Miscellaneous**: $134,146

## Cost-Per-Contact Rates

The following rates are used to project the budget for our canvassing program:

- **Door Knock**: $7.00 per door (average of 8 doors per hour)
- **Phone Call**: $1.50 per call
- **Text Message**: $0.05 per text
- **Mail Piece**: $1.00 per piece plus a $500 flat design fee
- **Digital**: $0.02 per impression with a $1,000 minimum per flight

## Strategic Considerations

- **Target Demographic**: Voters with inconsistent voting history
- **Key Message**: A comprehensive "serious about safety" platform that resonates particularly well with Black voters and young voters.

## Conclusion

Implementing a canvassing program in Virginia's 7th Congressional District will require careful budgeting and strategic allocation of resources across various outreach methods. By leveraging historical data and industry averages, we can effectively plan and execute a program that maximizes voter engagement and turnout.

*Research sourced from materials dated as recently as 2022.*

### Q3: Win number

> *What is the win number for Virginia's 7th Congressional District in 2026?*

**Pipeline time:** 5.77s  
**Agents called:** win_number  

**Final Answer:**

# Program Briefing: Virginia's 7th Congressional District Win Number for 2026

## Overview
As we strategize for the upcoming 2026 election cycle, it is crucial to understand the electoral dynamics of Virginia's 7th Congressional District. Our analysis focuses on the win number, projected turnout, and historical voting patterns to inform our campaign efforts.

## Key Findings

- **Win Number**: The win number for Virginia's 7th Congressional District in 2026 is projected to be **150,404** votes. This figure represents the minimum number of votes needed to secure a victory in the district.

- **Projected Turnout**: The anticipated voter turnout for the district is **289,239**. This projection is based on historical data from previous midterm election cycles, specifically 2014, 2018, and 2022.

- **Voter Universe**: The Citizen Voting Age Population (CVAP) for the district is estimated at **542,664**. This figure provides a broader context for understanding the potential voter base.

- **Average Turnout Percentage**: Historically, the average turnout percentage for the district is approximately **53.3%**. This average is derived from the same midterm cycles used for turnout projections.

- **Victory Margin**: The projected victory margin is **0.52%**, indicating a competitive race where every vote will be crucial.

## Strategic Implications

- **Targeted Outreach**: Given the competitive nature of the district, our campaign should prioritize targeted outreach to ensure we meet or exceed the win number of 150,404 votes.

- **Voter Engagement**: With a projected turnout of 289,239, our efforts should focus on maximizing voter engagement and turnout, particularly among key demographic groups within the CVAP.

- **Historical Context**: Understanding the historical context of previous election cycles will aid in refining our strategies to address any shifts in voter behavior or preferences.

*Research sourced from materials dated as recently as unknown.*

---

## Groq

| Field | Value |
|-------|-------|
| Completion model | `llama-3.1-70b-versatile` |

### Q1: Young voter targeting + messaging

> *I want to reach young voters in Virginia's 7th Congressional District. What precincts should I target and what message should I deliver?*

**Pipeline time:** 40.21s  
**Agents called:** researcher, election_results, win_number, precincts, messaging, cost_calculator  
**Non-fatal errors (1):** ElectionAnalyst: MEDSL party-level data unavailable — margin trend and D/R vote shares cannot be computed. Turnout data from master CSV will still be used.

**Final Answer:**

# Program Briefing: Engaging Young Voters in Virginia's 7th Congressional District

## Target Precincts

To effectively reach young voters in Virginia's 7th Congressional District, we should focus our efforts on precincts with the highest concentrations of young voters aged 18-34. The following precincts have been identified as key targets based on their youth voter population:

- **Trevvett**: Youth VAP of 1,942.73
- **51087-315-Tucker**: Youth VAP of 1,914.09
- **51041-105-DrewrysBluff**: Youth VAP of 1,826.16
- **51041-210-FiveForks**: Youth VAP of 1,749.47
- **51087-201-Azalea**: Youth VAP of 1,703.58
- **51087-105-Hermitage**: Youth VAP of 1,647.49
- **51087-110-Longan**: Youth VAP of 1,553.87
- **51041-207-Chippenham**: Youth VAP of 1,465.20
- **51177-103 - JOHN J. WRIGHT**: Youth VAP of 1,456.81
- **51041-412-CloverHill**: Youth VAP of 1,295.04

These precincts should be prioritized for outreach efforts due to their significant populations of young voters.

## Messaging Strategy

**Key Message:** Empowering young voices to shape their future.

### Messaging Themes
- **Informed Media Consumption**: Emphasize the importance of accessing reliable news sources to empower informed decision-making.
- **Public Safety**: Promote a comprehensive "serious about safety" platform that addresses prevention and response, resonating with young and Black voters.

### Media Behavior Insights
- **Young Men**: More likely to trust podcasts, Twitter/X, and YouTube.
- **Young Women**: Prefer TikTok, national and local TV news, and informational articles online.

### Messaging Channels
- **Digital Ads**: Utilize platforms like Facebook, Instagram, and display ads to reach young voters where they are most active.
- **Canvassing and Phone Banking**: Engage directly with voters through door-to-door canvassing and phone calls, emphasizing the importance of their vote.
- **Text Messaging**: Use peer-to-peer texting to provide concise, impactful messages and reminders about voting.

### Sample Messaging
- **Canvassing/Phone Banking**: "Candidate Name is committed to promoting informed media consumption and a balanced approach to safety. Can we count on your support?"
- **Digital Ads**: "Safety and Media Matter in 5107. Candidate Name is fighting for informed media and safety. Join us on Election Day."
- **Text Messaging**: "Hi [NAME]! I'm [CALLER], volunteering for Candidate Name in Congressional 5107. Can we count on your vote on Election Day? Reply STOP to opt out."

## Conclusion

By targeting the identified precincts and delivering a message that resonates with young voters' priorities, our campaign can effectively engage and mobilize this critical demographic.

*Research sourced from materials dated as recently as 2022.*

### Q2: Canvassing cost estimate

> *How much would it cost to run a canvassing program in Virginia's 7th Congressional District in 2026?*

**Pipeline time:** 44.92s  
**Agents called:** researcher, election_results, win_number, precincts, messaging, cost_calculator  
**Non-fatal errors (1):** ElectionAnalyst: MEDSL party-level data unavailable — margin trend and D/R vote shares cannot be computed. Turnout data from master CSV will still be used.

**Final Answer:**

# Program Briefing: Canvassing Cost Estimate for Virginia's 7th Congressional District in 2026

## Overview

Our campaign is considering a comprehensive canvassing program in Virginia's 7th Congressional District for the 2026 election. This briefing outlines the estimated costs and strategic considerations based on historical data and recent research findings.

## Estimated Costs

The cost estimates for running a canvassing program are derived from historical spending data and industry averages for Congressional races. The following are the key components of the budget:

- **Door Knocking:**
  - **Cost per Door Knock:** $7.00
  - **Average Doors per Hour:** 8
  - This cost includes the personnel expenses associated with canvassing efforts.

- **Total Program Estimate:**
  - **Total Estimated Cost:** $1,341,459
  - **Breakdown by Category:**
    - **Personnel:** $469,511
    - **Mail:** $268,292
    - **Digital:** $335,365
    - **Phones:** $134,146
    - **Miscellaneous:** $134,146

## Strategic Considerations

- **Target Demographic:** The canvassing efforts will focus on voters with inconsistent voting histories, as these individuals are more likely to be influenced by direct engagement.
  
- **Messaging Strategy:** 
  - Emphasize a comprehensive safety plan that addresses crime and resonates with key demographics, including Black and young voters.
  - Utilize a "serious about safety" platform that has shown positive reception in previous studies.

- **Historical Context:**
  - The district has a Cook Political Report PVI of D+6, indicating a lean Democratic advantage.
  - The projected turnout for 2026 is estimated at 289,239 voters, with a win number of 150,404.

## Conclusion

Implementing a canvassing program in Virginia's 7th Congressional District requires a significant investment, with personnel and direct voter contact being the primary cost drivers. The strategic focus on engaging voters with inconsistent voting histories and addressing key issues like safety will be crucial to maximizing the impact of our canvassing efforts.

*Research sourced from materials dated as recently as 2022.*

### Q3: Win number

> *What is the win number for Virginia's 7th Congressional District in 2026?*

**Pipeline time:** 5.63s  
**Agents called:** win_number  

**Final Answer:**

# Virginia's 7th Congressional District: 2026 Win Number Briefing

## Overview

As we strategize for the upcoming 2026 election cycle, understanding the win number for Virginia's 7th Congressional District is crucial. This figure represents the minimum number of votes needed to secure victory in the district.

## Key Findings

- **Win Number**: The projected win number for Virginia's 7th Congressional District in 2026 is **150,404** votes.
  
- **Projected Turnout**: The anticipated voter turnout for the district is **289,239**. This projection is based on historical data from previous midterm election cycles, specifically 2014, 2018, and 2022.

- **Voter Universe**: The total voter universe, or Citizen Voting Age Population (CVAP), in the district is **542,664**.

- **Average Turnout Percentage**: Historically, the average turnout percentage for midterm elections in this district has been approximately **53.3%**.

- **Victory Margin**: The expected victory margin is narrow, at **0.52%**, indicating a highly competitive race.

## Strategic Implications

- **Targeted Outreach**: Given the competitive nature of the district, our campaign must focus on targeted outreach to ensure we meet or exceed the win number.
  
- **Resource Allocation**: With a projected turnout of 289,239, efficient allocation of resources towards voter mobilization efforts will be essential to secure the necessary votes.

- **Historical Context**: Our strategy should consider trends and patterns from the 2014, 2018, and 2022 midterm elections to anticipate voter behavior and adjust our approach accordingly.

*Research sourced from materials dated as recently as unknown.*

---

## Llama

| Field | Value |
|-------|-------|
| Completion model | `llama-3.1-70b-versatile` |

### Q1: Young voter targeting + messaging

> *I want to reach young voters in Virginia's 7th Congressional District. What precincts should I target and what message should I deliver?*

**Pipeline time:** 43.93s  
**Agents called:** researcher, election_results, win_number, precincts, messaging, cost_calculator  
**Non-fatal errors (1):** ElectionAnalyst: MEDSL party-level data unavailable — margin trend and D/R vote shares cannot be computed. Turnout data from master CSV will still be used.

**Final Answer:**

# Program Briefing: Engaging Young Voters in Virginia's 7th Congressional District

## Target Precincts

To effectively reach young voters in Virginia's 7th Congressional District, we should focus on precincts with the highest concentrations of voters aged 18-34. The following precincts have been identified as key targets due to their significant youth voter populations:

- **Trevvett** (Youth VAP: 1,942.73)
- **Tucker** (Youth VAP: 1,914.09)
- **Drewrys Bluff** (Youth VAP: 1,826.16)
- **Five Forks** (Youth VAP: 1,749.47)
- **Azalea** (Youth VAP: 1,703.58)
- **Hermitage** (Youth VAP: 1,647.49)
- **Longan** (Youth VAP: 1,553.87)
- **Chippenham** (Youth VAP: 1,465.20)
- **John J. Wright** (Youth VAP: 1,456.81)

These precincts are prioritized based on their youth voter population, which is crucial for maximizing our outreach efforts.

## Messaging Strategy

To engage young voters effectively, our messaging should focus on empowering them to influence change on issues that matter most to them. Based on recent findings, the following key messages and strategies should be employed:

- **Empowerment and Influence**: Emphasize the power of young voters to drive change in their community. Highlight how their participation can influence critical issues like public safety and community well-being.
  
- **"Serious About Safety" Platform**: Promote a comprehensive approach to public safety that resonates with young and diverse voters. This includes preventing crime and responding to crises effectively, which has shown to align with the views of young voters.

- **Media Consumption**: Tailor our media strategy to align with the preferred platforms of young voters. Young men are more likely to trust podcasts, Twitter/X, and YouTube, while young women prefer TikTok, national TV news, and informational articles online. Our campaign should leverage these platforms to disseminate our message effectively.

- **Addressing Concerns**: Acknowledge and address common objections such as distrust in political news sources and the belief that their vote doesn't matter. Reinforce our campaign's commitment to transparency and the importance of their voice in the electoral process.

## Implementation

- **Canvassing and Phone Banking**: Utilize door-to-door canvassing and phone banking scripts that focus on empowering young voters and addressing their concerns. Ensure that canvassers and callers are well-versed in the "serious about safety" platform and can pivot conversations to address specific voter priorities.

- **Digital and Social Media**: Deploy targeted digital ads on platforms like Facebook, Instagram, and YouTube, emphasizing the stakes of the election and the importance of young voter participation. Use high-contrast visuals and clear calls to action to engage this demographic.

- **Text Messaging**: Implement a peer-to-peer texting campaign to reach young voters directly, providing them with information about voting and encouraging them to participate on Election Day.

By focusing on these targeted precincts and delivering a message that resonates with young voters, we can effectively engage this critical demographic and encourage their participation in the upcoming election.

*Research sourced from materials dated as recently as 2022.*

### Q2: Canvassing cost estimate

> *How much would it cost to run a canvassing program in Virginia's 7th Congressional District in 2026?*

**Pipeline time:** 40.36s  
**Agents called:** researcher, election_results, win_number, precincts, messaging, cost_calculator  
**Non-fatal errors (1):** ElectionAnalyst: MEDSL party-level data unavailable — margin trend and D/R vote shares cannot be computed. Turnout data from master CSV will still be used.

**Final Answer:**

# Program Briefing: Canvassing Program Cost in Virginia's 7th Congressional District for 2026

## Overview

Our campaign aims to implement a comprehensive canvassing program in Virginia's 7th Congressional District for the 2026 election cycle. This briefing outlines the estimated costs and strategic considerations based on historical data and recent research findings.

## Cost Estimates

### Total Campaign Disbursement
- **Average Total Campaign Disbursement**: $1,341,459

### Estimated Spending by Category
- **Personnel**: $469,511
- **Mail**: $268,292
- **Digital**: $335,365
- **Phones**: $134,146
- **Miscellaneous**: $134,146

### Per-Contact Rates
- **Door Knock**: $7.00 per door (8 doors/hour average)
- **Phone Call**: $1.50 per call
- **Text Message**: $0.05 per text
- **Mail Piece**: $1.00 per piece + $500 flat design fee
- **Digital**: $0.02 per impression ($1,000 minimum per flight)

## Strategic Considerations

### Target Demographics
- Focus on voters with inconsistent voting histories.
- Emphasize a comprehensive "serious about safety" platform which resonates particularly well with young and Black voters.

### Messaging Strategy
- Utilize a multi-channel approach including door-to-door canvassing, phone banking, text messaging, and digital ads.
- Highlight issues of voter turnout and crime, which are top concerns for the community.

### Historical Context
- The district is rated as **Lean Democratic** with a Cook PVI of **D+6**.
- The most recent election in 2022 had a total of 274,590 votes cast.

### Projected Turnout
- **Projected Turnout for 2026**: 289,239
- **Win Number**: 150,404

## Conclusion

Implementing a canvassing program in Virginia's 7th Congressional District will require strategic allocation of resources across various outreach methods. The estimated cost for such a program is approximately $1.34 million, with significant investments in personnel, digital outreach, and direct voter contact methods. Our focus will remain on engaging voters with inconsistent voting patterns and addressing their key concerns to maximize turnout and support.

*Research sourced from materials dated as recently as 2022.*

### Q3: Win number

> *What is the win number for Virginia's 7th Congressional District in 2026?*

**Pipeline time:** 6.04s  
**Agents called:** win_number  

**Final Answer:**

# Virginia's 7th Congressional District: 2026 Win Number Briefing

## Overview

In preparation for the 2026 election cycle, our campaign has focused on understanding the win number necessary to secure victory in Virginia's 7th Congressional District. This briefing outlines the key metrics and projections that will guide our strategic planning.

## Key Metrics

- **Win Number**: The projected win number for Virginia's 7th Congressional District in 2026 is **150,404** votes. This figure represents the minimum number of votes required to secure a majority in the upcoming election.
  
- **Projected Turnout**: We anticipate a voter turnout of **289,239** individuals. This projection is based on historical data from previous midterm elections in 2014, 2018, and 2022.

- **Voter Universe**: The voter universe, defined as the Citizen Voting Age Population (CVAP), is estimated at **542,664**. This figure provides the total pool of potential voters in the district.

- **Average Turnout Percentage**: Historically, the average turnout percentage for this district has been **53.3%**. This percentage reflects the proportion of the voter universe that is expected to participate in the election.

- **Victory Margin**: The projected victory margin is **0.52%**, indicating a competitive race where every vote will be crucial.

## Historical Context

The projections are informed by an analysis of past electoral cycles, specifically the midterm elections of 2014, 2018, and 2022. These cycles provide a contextual basis for understanding voter behavior and turnout trends in the district.

## Strategic Implications

- **Focus on Turnout**: Given the competitive nature of the district, our campaign must prioritize efforts to maximize voter turnout, particularly among our core supporters.

- **Targeted Outreach**: With a clear understanding of the voter universe, we should implement targeted outreach strategies to engage and mobilize undecided and infrequent voters.

- **Resource Allocation**: The projected win number and turnout figures will guide our resource allocation, ensuring that campaign efforts are effectively directed towards achieving the necessary vote count.

*Research sourced from materials dated as recently as unknown.*

---

## Mistral

| Field | Value |
|-------|-------|
| Completion model | `mistral-large-latest` |

### Q1: Young voter targeting + messaging

> *I want to reach young voters in Virginia's 7th Congressional District. What precincts should I target and what message should I deliver?*

**Pipeline time:** 39.50s  
**Agents called:** researcher, election_results, win_number, precincts, messaging, cost_calculator  
**Non-fatal errors (1):** ElectionAnalyst: MEDSL party-level data unavailable — margin trend and D/R vote shares cannot be computed. Turnout data from master CSV will still be used.

**Final Answer:**

# Program Briefing: Targeting Young Voters in Virginia's 7th Congressional District

## Target Precincts

To effectively reach young voters in Virginia's 7th Congressional District, we should focus on precincts with the highest concentrations of young voters aged 18-34. Based on our analysis, the following precincts are prioritized due to their significant youth voting-age population (youth VAP):

- **Trevvett**: 1,942.73 youth VAP
- **51087-315-Tucker**: 1,914.09 youth VAP
- **Drewrys Bluff**: 1,826.16 youth VAP
- **Five Forks**: 1,749.47 youth VAP
- **Azalea**: 1,703.58 youth VAP
- **Hermitage**: 1,647.49 youth VAP
- **Longan**: 1,553.87 youth VAP
- **Chippenham**: 1,465.20 youth VAP
- **- JOHN J. WRIGHT**: 1,456.81 youth VAP
- **Clover Hill**: 1,295.04 youth VAP

These precincts show a high concentration of young voters, making them ideal targets for our outreach efforts.

## Messaging Strategy

Our messaging should focus on empowering young voters by addressing issues that resonate with them, particularly public safety and media trust. The following key messages and strategies should be employed:

- **Empowerment and Impact**: Emphasize the power of young voters to make impactful changes on issues that matter to them. Highlight the importance of their participation in shaping policies that affect their future.

- **Public Safety**: Promote a comprehensive "serious about safety" platform that includes crime prevention and effective crisis response. This message resonates strongly with young voters and aligns with their priorities.

- **Media Trust**: Acknowledge the diverse media consumption habits of young voters. Ensure that our campaign provides accurate and impactful information through trusted channels.

- **Tailored Outreach**: Use different media platforms to reach young men and women effectively. For young men, focus on podcasts, Twitter/X, and YouTube. For young women, prioritize TikTok, national TV news, and online articles.

## Communication Channels

- **Door-to-Door Canvassing**: Engage young voters directly with a personal touch. Use a script that highlights the candidate's commitment to safety and youth engagement.

- **Phone Banking**: Connect with young voters to discuss their concerns and the candidate's stance on key issues. Ensure calls are concise and respectful of the voter's time.

- **Text Messaging**: Utilize peer-to-peer texting to reach young voters quickly and efficiently. Keep messages short, informative, and include an opt-out option.

- **Digital Advertising**: Run targeted ads on platforms like Facebook and Instagram to reach young voters where they are most active. Use high-contrast visuals and clear calls to action.

## Conclusion

By focusing on these targeted precincts and delivering a message that resonates with young voters, we can effectively engage this demographic and encourage their participation in the upcoming election. Our strategy leverages both traditional and digital communication channels to maximize outreach and impact.

*Research sourced from materials dated as recently as 2022.*

### Q2: Canvassing cost estimate

> *How much would it cost to run a canvassing program in Virginia's 7th Congressional District in 2026?*

**Pipeline time:** 41.15s  
**Agents called:** researcher, election_results, win_number, precincts, messaging, cost_calculator  
**Non-fatal errors (1):** ElectionAnalyst: MEDSL party-level data unavailable — margin trend and D/R vote shares cannot be computed. Turnout data from master CSV will still be used.

**Final Answer:**

# Program Briefing: Canvassing Cost Estimate for Virginia's 7th Congressional District in 2026

## Overview

Our campaign is considering implementing a comprehensive canvassing program in Virginia's 7th Congressional District for the 2026 election. This briefing provides an estimate of the costs associated with running such a program based on historical spending data and current cost-per-contact rates.

## Historical Spending and Cost Estimates

The average total campaign disbursement for comparable Congressional races in this district, based on data from the 2018 and 2022 election cycles, was approximately **$1,341,459**. This figure provides a baseline for understanding the financial scope of a full campaign effort, including canvassing.

### Estimated Spending by Category

- **Personnel:** $469,511
- **Mail:** $268,292
- **Digital:** $335,365
- **Phones:** $134,146
- **Miscellaneous:** $134,146

### Per-Contact Rates

The following cost-per-contact rates are used for budget projections:

- **Door Knock:** $7.00 per door (average of 8 doors per hour)
- **Phone Call:** $1.50 per call
- **Text Message:** $0.05 per text
- **Mail Piece:** $1.00 per piece plus a $500 flat design fee
- **Digital Advertising:** $0.02 per impression (with a $1,000 minimum per flight)

## Canvassing Program Focus

Our canvassing efforts will primarily target voters with inconsistent voting histories, as research indicates that canvassing can have a positive impact on turnout among this demographic. The messaging will focus on:

- **Crime and Safety:** Emphasizing a comprehensive "serious about safety" platform that resonates particularly well with Black and young voters.
- **Voter Turnout:** Encouraging participation by highlighting the importance of each vote in contributing to community safety and change.

## Conclusion

Implementing a canvassing program in Virginia's 7th Congressional District will require careful financial planning and strategic targeting to maximize voter engagement and turnout. By leveraging historical spending data and current cost-per-contact rates, we can effectively allocate resources to achieve our campaign goals.

*Research sourced from materials dated as recently as 2022.*

### Q3: Win number

> *What is the win number for Virginia's 7th Congressional District in 2026?*

**Pipeline time:** 5.59s  
**Agents called:** win_number  

**Final Answer:**

## Program Briefing: Virginia's 7th Congressional District Win Number for 2026

In our strategic planning for the 2026 midterm elections, understanding the win number for Virginia's 7th Congressional District is crucial. Based on the most recent and specific data available, here is the synthesized information:

- **Win Number**: The win number for Virginia's 7th Congressional District in 2026 is projected to be **150,404** votes.
  
- **Projected Turnout**: The anticipated voter turnout for the district is **289,239**. This projection is based on historical turnout data from previous midterm election cycles, specifically 2014, 2018, and 2022.

- **Voter Universe**: The Citizen Voting Age Population (CVAP) for the district is estimated at **542,664**.

- **Average Turnout Percentage**: The average turnout percentage for the district, derived from past midterm cycles, is **53.3%**.

- **Victory Margin**: A narrow victory margin of **0.52%** is expected, indicating a highly competitive race.

- **Historical Context**: The projections are based on an analysis of voter behavior and turnout patterns from the 2014, 2018, and 2022 midterm elections.

This data will guide our campaign strategy as we aim to secure a victory in this pivotal district. By focusing on mobilizing our base and reaching out to undecided voters, we can achieve the necessary win number to succeed.

*Research sourced from materials dated as recently as unknown.*

---

## Openai

| Field | Value |
|-------|-------|
| Completion model | `gpt-4o` |

### Q1: Young voter targeting + messaging

> *I want to reach young voters in Virginia's 7th Congressional District. What precincts should I target and what message should I deliver?*

**Pipeline time:** 49.79s  
**Agents called:** researcher, election_results, win_number, precincts, messaging, cost_calculator  
**Non-fatal errors (1):** ElectionAnalyst: MEDSL party-level data unavailable — margin trend and D/R vote shares cannot be computed. Turnout data from master CSV will still be used.

**Final Answer:**

# Program Briefing: Targeting Young Voters in Virginia's 7th Congressional District

## Target Precincts

To effectively reach young voters in Virginia's 7th Congressional District, we should focus on precincts with the highest concentrations of young voters aged 18-34. Based on the latest data, the following precincts have been identified as priorities:

- **Trevvett**: Youth VAP of 1,942.73
- **Tucker**: Youth VAP of 1,914.09
- **Drewrys Bluff**: Youth VAP of 1,826.16
- **Five Forks**: Youth VAP of 1,749.47
- **Azalea**: Youth VAP of 1,703.58

These precincts have been selected due to their significant youth voter populations, making them strategic targets for our outreach efforts.

## Messaging Strategy

### Key Message Themes

Our messaging should focus on issues that resonate with young voters, particularly around safety and media trust. The following themes should be emphasized:

- **Empowerment**: Highlight the power of young voters to drive change on issues that matter to them.
- **Safety**: Promote a comprehensive "serious about safety" platform that addresses crime prevention, crisis response, and violence prevention. This message has shown strong resonance with young and Black voters.
- **Media Trust**: Acknowledge the different media consumption habits of young men and women, and emphasize the importance of understanding media sources and their influence.

### Media Channels

Given the varied media consumption habits of young voters, our outreach should be tailored accordingly:

- **Podcasts, Twitter/X, and YouTube**: Target young men who are more likely to trust these platforms.
- **TikTok, National and Local TV News**: Engage young women who prefer these sources.
- **Online Articles**: Utilize for broader reach, as they are trusted by a significant portion of young voters.

### Messaging Formats

- **Door-to-Door Canvassing**: Use a script that emphasizes empowering young voices and addresses concerns about safety and media trust.
- **Phone Banking**: Focus on quick, engaging conversations that highlight the candidate's stance on key issues.
- **Text Messaging**: Send concise, targeted messages with clear calls to action.
- **Mail and Digital Ads**: Use visually appealing and informative content to reinforce our key messages.

## Budget Considerations

Based on historical spending patterns, the estimated budget for reaching young voters in this district includes:

- **Personnel**: $469,511
- **Mail**: $268,292
- **Digital**: $335,365
- **Phones**: $134,146
- **Miscellaneous**: $134,146

These allocations are based on industry averages for Congressional races and should guide our financial planning.

*Research sourced from materials dated as recently as 2022.*

### Q2: Canvassing cost estimate

> *How much would it cost to run a canvassing program in Virginia's 7th Congressional District in 2026?*

**Pipeline time:** 54.10s  
**Agents called:** researcher, election_results, win_number, precincts, messaging, cost_calculator  
**Non-fatal errors (1):** ElectionAnalyst: MEDSL party-level data unavailable — margin trend and D/R vote shares cannot be computed. Turnout data from master CSV will still be used.

**Final Answer:**

# Virginia's 7th Congressional District Canvassing Program Briefing

## Overview

Our campaign is considering the implementation of a comprehensive canvassing program in Virginia's 7th Congressional District for the 2026 election cycle. This briefing outlines the estimated costs and strategic considerations based on historical data and recent research findings.

## Estimated Costs

The cost to run a canvassing program in Virginia's 7th Congressional District is based on historical spending patterns and industry averages for similar congressional races. Below are the estimated costs:

- **Total Estimated Cost:** $1,341,459
  - **Personnel:** $469,511
  - **Mail:** $268,292
  - **Digital:** $335,365
  - **Phones:** $134,146
  - **Miscellaneous:** $134,146

### Per-Contact Rates

- **Door Knock:** $7.00 per door (average 8 doors/hour)
- **Phone Call:** $1.50 per call
- **Text Message:** $0.05 per text
- **Mail Piece:** $1.00 per piece + $500 flat design fee
- **Digital:** $0.02 per impression ($1,000 minimum per flight)

## Strategic Considerations

- **Target Demographic:** Our focus will be on voters with inconsistent voting histories, as canvassing has shown positive downstream effects on turnout, particularly among this group.
- **Messaging:** The key message will revolve around increasing voter turnout and addressing crime concerns with a comprehensive safety plan. This message has resonated well with young and Black voters, as indicated by recent ad tests and polling data.
- **Competitiveness:** The district is rated as "Lean D" with a Cook PVI of D+6. The projected turnout for 2026 is 289,239, with a win number of 150,404 votes needed for victory.

## Implementation

- **Canvassing Script:** Our door-to-door canvassing script will focus on engaging voters in meaningful conversations about safety and civic engagement. We will leave behind palm cards with the candidate's safety plan and voting information.
- **Phone Banking and Texting:** These efforts will complement our door-to-door canvassing, targeting the same demographic with a consistent message.
- **Digital and Mail Campaigns:** These will be used to reinforce our message and reach voters who may not be accessible through direct contact methods.

*Research sourced from materials dated as recently as 2022.*

### Q3: Win number

> *What is the win number for Virginia's 7th Congressional District in 2026?*

**Pipeline time:** 6.18s  
**Agents called:** win_number  

**Final Answer:**

# Program Briefing: Win Number for Virginia's 7th Congressional District in 2026

## Overview

In preparation for the upcoming 2026 election cycle, it is crucial for our campaign to understand the win number necessary to secure victory in Virginia's 7th Congressional District. This briefing outlines the key metrics and projections that will guide our strategic planning.

## Key Metrics

- **Win Number**: The projected win number for Virginia's 7th Congressional District in the 2026 midterm elections is **150,404** votes.
- **Projected Turnout**: We anticipate a voter turnout of approximately **289,239** individuals.
- **Voter Universe**: The Citizen Voting Age Population (CVAP) for the district is estimated at **542,664**.
- **Average Turnout Percentage**: Historically, the average turnout percentage for this district is **53.3%**.
- **Victory Margin**: A narrow victory margin of **0.52%** is projected, emphasizing the need for a robust and targeted campaign strategy.

## Historical Context

The win number and turnout projections are based on an analysis of previous midterm election cycles, specifically the years **2014, 2018, and 2022**. These cycles provide a historical context that informs our current projections and strategic approach.

## Strategic Implications

- **Targeted Outreach**: Given the narrow victory margin, our campaign must focus on targeted outreach to key demographics within the district to ensure we meet or exceed the projected win number.
- **Voter Engagement**: Increasing voter engagement and turnout will be critical. Strategies should include grassroots mobilization, digital engagement, and community events.
- **Resource Allocation**: Efficient allocation of campaign resources will be necessary to maximize impact and reach the projected win number.

*Research sourced from materials dated as recently as unknown.*

---

## Full Pipeline Timing Summary

| Provider | Query | Total Time | Agents |
|----------|-------|------------|--------|
| anthropic    | canvassing_cost      | 36.39s     | 6 |
| anthropic    | win_number           | 4.90s      | 1 |
| anthropic    | young_voters         | 42.59s     | 6 |
| cohere       | canvassing_cost      | 39.10s     | 6 |
| cohere       | win_number           | 6.57s      | 1 |
| cohere       | young_voters         | 35.98s     | 6 |
| gemini       | canvassing_cost      | 42.66s     | 6 |
| gemini       | win_number           | 5.77s      | 1 |
| gemini       | young_voters         | 42.06s     | 6 |
| groq         | canvassing_cost      | 44.92s     | 6 |
| groq         | win_number           | 5.63s      | 1 |
| groq         | young_voters         | 40.21s     | 6 |
| llama        | canvassing_cost      | 40.36s     | 6 |
| llama        | win_number           | 6.04s      | 1 |
| llama        | young_voters         | 43.93s     | 6 |
| mistral      | canvassing_cost      | 41.15s     | 6 |
| mistral      | win_number           | 5.59s      | 1 |
| mistral      | young_voters         | 39.50s     | 6 |
| openai       | canvassing_cost      | 54.10s     | 6 |
| openai       | win_number           | 6.18s      | 1 |
| openai       | young_voters         | 49.79s     | 6 |

---

## ChangeAgent

ChangeAgent: pending API integration

_This section will be populated automatically once ChangeAgent is registered via `register_custom_provider()` in llm_config.py._

---
