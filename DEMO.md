# [APP_NAME] Demo: Run-of-Show

**Audience:** Funders, partner organizations, prospective clients, advisory board.
**Length:** 10-12 minutes live; 5 minutes for the short version.
**Setting:** Screen share; one operator (Rosario or Ben) drives, one narrator presents.

---

## Pre-demo checklist (do this 30 minutes before)

- [ ] Open https://powerbuilder.app in a fresh browser window. Have the demo password (`WeWriteYouWin26!`) ready in a paste buffer.
- [ ] Have `data/demo/gwinnett_demo_voterfile.csv` open in a Finder/Explorer window, ready to drag in.
- [ ] Confirm `DEMO_MODE=1` is set on the deployed instance (deterministic, audience-safe outputs).
- [ ] Close Slack, email, calendar notifications.
- [ ] Have a backup terminal open with the local instance running at `localhost:8000` in case the live site has a hiccup.
- [ ] Open this run-of-show in a side window for the operator to follow.

---

## The story (90-second narrator intro)

> We built [APP_NAME] because the strategic planning and research synthesis available to large, well-resourced civic programs should also be available to a county-level voter education effort, a community-based organizing group, or a local nonprofit running a nonpartisan turnout push.
>
> Today I'll walk you through one real workflow: an organizer in Gwinnett County, Georgia wants a get-out-the-vote plan for Latinx voters age 18 to 35, with a Spanish door-knock script and an exportable target list. In a traditional shop this is a week of analyst time. We're going to do it in about three minutes.

---

## Act 1: Open the app and set the scene (~1 minute)

1. **Land on the login page.** Mention: "Single password gate today; SSO and per-org accounts are next on the roadmap. Every org gets its own private namespace inside our research vector store, so uploaded data never crosses orgs."
2. **Log in.** The chat UI appears.
3. **Point to the paperclip icon.** "We can ingest documents (voter files, internal research, opposition books) and the AI will use them as a private research source for that org only."

## Act 2: Voter file upload (~2 minutes)

1. **Drag in `gwinnett_demo_voterfile.csv`.** A confirmation appears in the chat.
2. **Narrator says:** "This is a 50,000-row synthetic file shaped exactly like a real TargetSmart export. The system is going to recognize the vendor, standardize the columns, and segment the file before we even ask a question."
3. **Type into the chat:**

   > Build a Gwinnett County GOTV plan targeting Latinx voters age 18-35. Generate a Spanish door-knock script and give me a CSV of the target list.

4. **Send.** Watch the agent log appear in real time.

### What to narrate while the agents run

- **"Voter File Agent is running."** "It detected this as a TargetSmart export and is segmenting now: by age cohort, by party, by race, by turnout tier. About 27 fields mapped from a real-vendor schema."
- **"Researcher is running."** "It's pulling from two places at once: a curated public corpus we maintain, and any private research this org has uploaded. Today it'll lean on the public corpus: Analyst Institute field experiments, CIRCLE youth voting research, Equis Research on Latinx messaging, our own Gwinnett County context brief."
- **"Messaging Agent is running."** "Notice it's grounded: every claim in the script will trace back to a finding the researcher just retrieved. It's not making up statistics. And because the request said 'Spanish,' the messaging is producing native Spanish copy with the right register (tú-form for door knocks, usted for older voters)."
- **"Cost Calculator is running."** "It's pricing the program using our cost-per-contact rates."
- **"Synthesizer is running."** "It's assembling the deliverable now."

## Act 3: The output (~3 minutes)

The deliverable appears in the chat. Walk through it section by section:

1. **The header.** Names the district, the segment, and the date range of the research.
2. **The segment summary.** "5,178 Latinx voters age 18-35 in this file. Average Spanish-language score 71. Of those, 1,129 are in our highest-value tier for this program: Med-High to High turnout propensity, matched to our outreach criteria."
3. **The Spanish door-knock script.** Read the opening line aloud:
   > "Buenas, soy María con la campaña. ¿Prefiere que sigamos en español o en inglés?"

   Narrator: "That single line is the most-tested door opener for Latinx voters in Sun Belt suburbs. Lead in Spanish, switch on cue. The system knows that because it's in the curated playbook the researcher just pulled."
4. **The talking points.** Each is tied to a research source. "Notice, every claim has a citation: the Census data on Gwinnett's renter share, the public policy context on housing, the field benchmark on door + SMS compounding."
5. **The cost summary.** "About $13 per conversion at volunteer-driven canvass rates. The system pulled those benchmarks from our public field operations corpus."

## Act 4: The CSV export (~1 minute)

1. **Click the CSV download link.**
2. **Open it.** Show the columns: voter_id, name, address, precinct, language preference, demo flags, ranked tier.
3. **Narrator:** "This is what an organizer takes into the field tomorrow morning. Drop it into MiniVAN, hand it to the canvass team, and the targeting work that would have taken a week of analyst time is done."

## Act 5: Close (~1 minute)

> What you just saw runs on a stack we maintain in-house: Django plus LangGraph for the agent orchestration, Pinecone for the research corpus, real US Census and FEC data for the geographic and electoral analysis. The messaging agent is multi-language out of the box (Spanish, Mandarin, Vietnamese, Korean) because Gwinnett County, where we built the demo, is functionally a multilingual electorate, and so are the suburbs that decide every Sun Belt cycle.
>
> What I want you to take away: this is not a chatbot. This is a coordinator that knows when to call which specialist, holds them accountable to the research, and produces field-ready deliverables in the time it takes to make coffee.
>
> Questions?

---

## Common questions and prepared answers

**Q: How do you handle hallucination?**
A: The messaging agent is hard-constrained to draw only from researcher findings. The prompt explicitly forbids inventing statistics or polling numbers. The synthesizer carries citations into the final deliverable. We can show you the prompt; it's not a black box.

**Q: What about voter file privacy?**
A: Voter file data is processed in memory and discarded at the end of the request. Nothing is persisted to disk or to the vector store. Per-org research is stored in an isolated Pinecone namespace keyed off the user's email domain.

**Q: Does this replace organizers / analysts / consultants?**
A: No. It does the work that would otherwise not happen at all: the rural county the analyst doesn't have time for, the civic education program with no research budget, the language-specific outreach the organizer would have winged. The programs that already have a strategy team get a faster strategy team.

**Q: What languages does it support?**
A: Spanish, Mandarin, Vietnamese, Korean today. Adding a language is a one-file change in `chat/agents/messaging.py` (we just register the language code and a short style note). Any language is feasible; we prioritized the ones with the largest non-English-speaking populations in Gwinnett and similar Sun Belt suburbs.

**Q: How is this different from [generic AI chat product]?**
A: A generic chat product gives you a paragraph. [APP_NAME] gives you a plan, a script in the right language, a cost model, and a target CSV, grounded in field-tested research, in the time it takes to ask. The orchestration layer is the product.

**Q: What's the business model?**
A: We're designing this for nonpartisan civic engagement nonprofits, the 501(c)(3) world: voter education programs, community-based organizations, civic research groups, and coalitions doing nonpartisan turnout work. We're still finalizing pricing, but the direction is a tiered subscription scaled to program size rather than seat count, so field teams aren't penalized for adding volunteers. The fellowship-stage version you're seeing today is being shared with a small set of partner organizations for feedback and case studies.

---

## If something goes wrong

- **Live site is slow or down:** Switch the screen share to the local instance running at `localhost:8000`. Same flow, same output.
- **Spanish output comes back in English:** Stop the demo, refresh, retry. If it still fails, the language detection regex didn't match. Open the browser console, show "agent log: language_intent=es" if present, and acknowledge: "the language directive plumbing got skipped (known edge case, fix is queued)." Don't try to debug live.
- **CSV download fails:** Show the on-screen target list and tell the audience the export endpoint is in maintenance. Email them the file after the demo.
- **An agent times out:** "We're pulling live Census and FEC data; sometimes those APIs are slow. Let me restart that step." Re-send the request.

---

## Post-demo

- [ ] Email each attendee a follow-up within 24 hours with: the deliverable from the demo as a PDF, a link to powerbuilder.app, and a calendar link.
- [ ] Log notes in the partner CRM.
- [ ] If the demo surfaced a feature request, file it as an issue on `benoh20/dxp` and tag it `from-demo`.
