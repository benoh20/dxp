from dotenv import load_dotenv
load_dotenv()

from langgraph.graph import StateGraph, END
from .state import AgentState
from ..utils.llm_config import get_completion_client

from .researcher import research_node
from .ingestor import ingestor_node
from .precincts import PrecinctsAgent
from .win_number import WinNumberAgent
from .messaging import messaging_node
from .finance_agent import finance_node
from .export import export_node
from .election_results import ElectionAnalystAgent
from .voterfile_agent import VoterFileAgent
from .opposition_research import OppositionResearchAgent


# Define LLM and temperature for workflow
def get_model():
    return get_completion_client(temperature=0.3)


def _detect_demographic_intent(query: str) -> str:
    """
    Keyword scan that returns one or more demographic intent labels joined by "+".
    All matching intents are collected (e.g. "black+hispanic" for combined queries).
    Returns "default" when no specific demographic is detected.
    """
    q = query.lower()
    matches: list = []

    # "college student" for youth; plain "college" omitted to avoid conflict with "college educated"
    if any(kw in q for kw in ("young voter", "youth", "student", "college student", "millennial", "gen z", "young people")):
        matches.append("youth")
    if any(kw in q for kw in ("hispanic", "latino", "latina", "latinx", "spanish-speaking", "spanish speaking")):
        matches.append("hispanic")
    if any(kw in q for kw in ("black voter", "black voters", "african american", "hbcu")):
        matches.append("black")
    if any(kw in q for kw in ("asian", "aapi", "asian american", "pacific islander", "korean", "chinese", "vietnamese", "filipino", "japanese", "south asian", "indian american")):
        matches.append("aapi")
    if any(kw in q for kw in ("native american", "indigenous", "tribal", "american indian", "alaska native")):
        matches.append("native")
    if any(kw in q for kw in ("senior", "elderly", "older voter", "retiree", "65 plus", "65+", "aarp")):
        matches.append("senior")
    if any(kw in q for kw in ("college educated", "educated voter", "degree holder", "professional class")):
        matches.append("educated")
    if any(kw in q for kw in ("working class", "blue collar", "no college", "trade worker", "union")):
        matches.append("working_class")
    if any(kw in q for kw in ("low income", "poverty", "poor", "economically disadvantaged", "public housing")):
        matches.append("low_income")
    if any(kw in q for kw in ("high income", "wealthy", "affluent", "upper income", "high earner")):
        matches.append("high_income")
    if any(kw in q for kw in ("immigrant", "foreign born", "foreign-born", "naturalized", "new american", "refugee")):
        matches.append("immigrant")
    if any(kw in q for kw in ("veteran", "military", "armed forces", "service member", "former military")):
        matches.append("veteran")
    if any(kw in q for kw in ("suburban", "suburbs", "homeowner", "owner-occupied", "single family")):
        matches.append("suburban")
    if any(kw in q for kw in ("renter", "apartment", "urban renter", "tenant")):
        matches.append("renter")

    if not matches:
        return "default"
    return "+".join(matches)

# Keyword-based fast path for voter file queries — avoids an LLM call for clear cases.
_VOTER_FILE_KEYWORDS = (
    "voter file", "voterfile", "voter list", "my list", "upload list",
    "target list", "van export", "voter data", "contact list",
)

def _is_voter_file_query(query: str) -> bool:
    q = query.lower()
    return any(kw in q for kw in _VOTER_FILE_KEYWORDS)


# Keyword-based fast path for opposition research queries.
_OPP_RESEARCH_KEYWORDS = (
    "republican candidate", "opposing candidate", "opposition research",
    "vulnerabilities", "opponent", "other side",
)

def _is_opposition_research_query(query: str) -> bool:
    q = query.lower()
    return any(kw in q for kw in _OPP_RESEARCH_KEYWORDS)


# District reference detection — geographic agents require a specific district.
_DISTRICT_KEYWORDS = (
    "congressional district", "district", "senate district",
    "state senate", "state house", "governor",
)

def _has_district_reference(query: str) -> bool:
    q = query.lower()
    return any(kw in q for kw in _DISTRICT_KEYWORDS)


def voter_file_post_router(state: AgentState) -> str:
    """
    After voter_file runs: skip geographic agents when no district is mentioned.
    Routes directly to researcher so the segment research queries are fulfilled
    without detour through election_results / win_number / precincts.
    """
    if _has_district_reference(state.get("query", "")):
        return "intent_router"
    return "researcher"


# Check if a file needs to be ingested first
def triage_router(state: AgentState):
    if state.get("uploaded_file_path"):
        return "ingestor"
    return "intent_router"

# Intent Router / Classification
def intent_router_node(state: AgentState):
    # Fast path: skip LLM for unambiguous voter file queries — only when a file
    # is actually present; keyword match alone must not route to voter_file.
    active_agents  = state.get("active_agents", [])
    if (
        _is_voter_file_query(state["query"])
        and state.get("uploaded_file_path")
        and "voter_file" not in active_agents
    ):
        return {
            "router_decision":    "voter_file",
            "output_format":      "markdown",
            "demographic_intent": "default",
        }

    # Fast path: opposition research queries — run election_results first to get
    # the incumbent name, then opposition_research, without an LLM routing call.
    if _is_opposition_research_query(state["query"]):
        demographic = _detect_demographic_intent(state["query"])
        if "election_results" not in active_agents:
            return {
                "router_decision":    "election_results",
                "output_format":      "markdown",
                "demographic_intent": demographic,
            }
        if "opposition_research" not in active_agents:
            return {
                "router_decision":    "opposition_research",
                "output_format":      "markdown",
                "demographic_intent": demographic,
            }

    # Fast path: voter file sequence (no district) — after voter_file, force
    # researcher → messaging → cost_calculator → finish, skipping geographic agents.
    if "voter_file" in active_agents and not _has_district_reference(state["query"]):
        demographic = _detect_demographic_intent(state["query"])
        if "researcher" not in active_agents:
            return {"router_decision": "researcher",       "output_format": "markdown", "demographic_intent": demographic}
        if "messaging" not in active_agents:
            return {"router_decision": "messaging",        "output_format": "markdown", "demographic_intent": demographic}
        if "cost_calculator" not in active_agents:
            return {"router_decision": "cost_calculator",  "output_format": "markdown", "demographic_intent": demographic}
        return     {"router_decision": "finish",           "output_format": "markdown", "demographic_intent": demographic}

    llm = get_model()

    active_agents  = state.get("active_agents", [])
    res_len        = len(state.get("research_results", []))
    data_len       = len(state.get("structured_data", []))
    active_display = ", ".join(active_agents) if active_agents else "none"

    prompt = f"""
    You are a Senior Political Strategist and Advisor. You coordinate specialist agents to fulfill the user's request.

    User's Request:
    "{state['query']}"

    Agents already completed (do NOT repeat these): {active_display}
    Research memos collected: {res_len}
    Structured data points collected: {data_len}

    Available specialists:
    - RESEARCHER: Gathers qualitative insights from documents, reports, and research databases.
    - WIN_NUMBER: Calculates votes needed to win based on Census CVAP, historical turnout, and district type.
    - PRECINCTS: Identifies and ranks target precincts with voter demographic breakdowns.
    - ELECTION_RESULTS: Analyzes past election results, vote shares, and historical trends.
    - OPPOSITION_RESEARCH: Retrieves Republican candidate research books from American Bridge Research Books. Returns vulnerability analysis, contrast messaging angles, and attacks to avoid. Runs after ELECTION_RESULTS in full plans and messaging requests; skip for win-number-only or precinct-only queries.
    - MESSAGING: Generates canvassing scripts, text messages, mail narratives, and digital ad copy grounded in research.
    - COST_CALCULATOR: Estimates cost of campaign tactics (canvassing, phone banking, digital ads, mailers).
    - VOTER_FILE: Analyzes an uploaded voter file (CSV or Excel). Segments voters by age cohort, gender, party, and turnout history, then matches messaging research from the research library to each segment.
    - FINISH: All needed agents have run — proceed to final synthesis.

    DECISION RULES:

    1. POLITICAL PLAN REQUEST: If the user is asking for a political plan, program plan, or comprehensive campaign strategy, you must run agents in this exact order, returning the single next agent that has NOT yet appeared in the "Agents already completed" list:
       Step 1 → RESEARCHER
       Step 2 → ELECTION_RESULTS
       Step 3 → OPPOSITION_RESEARCH
       Step 4 → WIN_NUMBER
       Step 5 → PRECINCTS
       Step 6 → MESSAGING
       Step 7 → COST_CALCULATOR
       Step 8 → FINISH
       FORMAT: MARKDOWN

    2. VOTER FILE REQUEST: Only return VOTER_FILE if an uploaded_file_path is present in state (file_uploaded={bool(state.get("uploaded_file_path"))}). If no file is uploaded, do NOT return VOTER_FILE even if the user mentions voter files.

    3. SINGLE-TOPIC REQUEST: If the user asks a focused question, return only the single most relevant specialist. If you already have enough information to answer, return FINISH.
       Exception: if the question is about a Republican candidate, opponent vulnerabilities, or opposition research for a specific district, always run ELECTION_RESULTS first (to get the incumbent name), then OPPOSITION_RESEARCH, then FINISH — even for single-topic queries.

    IMPORTANT: Never return an agent that already appears in "Agents already completed."

    Return ONLY this line: DECISION: [specialist name], FORMAT: [markdown|csv|text]
    """

    response = llm.invoke(prompt).content.upper()

    # Order matters: longer/more specific strings must come before substrings.
    specialists = [
        "OPPOSITION_RESEARCH",
        "ELECTION_RESULTS",
        "COST_CALCULATOR",
        "VOTER_FILE",
        "WIN_NUMBER",
        "RESEARCHER",
        "PRECINCTS",
        "MESSAGING",
        "FINISH",
    ]
    decision = next((s for s in specialists if s in response), "FINISH")

    # Safety guard: never route to voter_file without an uploaded file,
    # regardless of what the LLM returned.
    if decision == "VOTER_FILE" and not state.get("uploaded_file_path"):
        decision = "RESEARCHER"

    formats = ["CSV", "MARKDOWN", "TEXT"]
    fmt = next((f for f in formats if f in response), "TEXT").lower()

    return {
        "router_decision":    decision.lower(),
        "output_format":      fmt,
        "demographic_intent": _detect_demographic_intent(state["query"]),
    }

# Constructing workflow for user request
workflow = StateGraph(AgentState)

# adding in all agents here
workflow.add_node("triage_router", lambda state: state)
workflow.add_node("intent_router", intent_router_node)

workflow.add_node("researcher", research_node)
workflow.add_node("ingestor", ingestor_node)
workflow.add_node("precincts", PrecinctsAgent.run)
workflow.add_node("win_number", WinNumberAgent.run)
workflow.add_node("messaging", messaging_node)
workflow.add_node("cost_calculator", finance_node)
workflow.add_node("election_results", ElectionAnalystAgent.run)
workflow.add_node("opposition_research", OppositionResearchAgent.run)
workflow.add_node("voter_file", VoterFileAgent.run)

workflow.add_node("synthesizer", export_node)

# workflow.add_node("export", export_node)

# Set pathways and routing logic via edges
workflow.set_entry_point("triage_router")

workflow.add_conditional_edges(
    "triage_router",
    triage_router,
    {
        "ingestor": "ingestor",
        "intent_router": "intent_router"
    }
)

workflow.add_edge("ingestor", "intent_router")

workflow.add_conditional_edges(
    "intent_router",
    lambda state: state["router_decision"],
    {
        "researcher":       "researcher",
        "precincts":        "precincts",
        "win_number":       "win_number",
        "messaging":        "messaging",
        "cost_calculator":  "cost_calculator",
        "election_results":   "election_results",
        "opposition_research":"opposition_research",
        "voter_file":         "voter_file",
        "finish":           "synthesizer",
    }
)


# Every agent loops back to intent_router so the orchestrator can decide the next step
workflow.add_edge("researcher",    "intent_router")
workflow.add_edge("precincts",     "intent_router")
workflow.add_edge("win_number",    "intent_router")
workflow.add_edge("messaging",        "intent_router")
workflow.add_edge("cost_calculator",  "intent_router")
workflow.add_edge("election_results",   "intent_router")
workflow.add_edge("opposition_research","intent_router")
workflow.add_conditional_edges(
    "voter_file",
    voter_file_post_router,
    {
        "researcher":    "researcher",
        "intent_router": "intent_router",
    }
)

workflow.add_edge("synthesizer", END)

manager_app = workflow.compile()


# ---------------------------------------------------------------------------
# View-facing helper
# ---------------------------------------------------------------------------

def run_query(
    query: str,
    org_namespace: str,
    output_format: str = "markdown",
    uploaded_file_path: str | None = None,
    recursion_limit: int = 50,
) -> dict:
    """
    Execute the Powerbuilder pipeline for a single user query.

    This is the only entry point that Django views should call.
    It ensures org_namespace is always injected into AgentState from
    a trusted source (the session), never from the HTTP request body.

    Args:
        query:              The user's natural-language question.
        org_namespace:      Pinecone namespace from request.session — scopes
                            all reads and writes to the correct org.
        output_format:      One of 'markdown', 'text', 'docx', 'xlsx', 'csv'.
        uploaded_file_path: Local path to a file for the ingestor, if any.
        recursion_limit:    LangGraph recursion cap (default 50).

    Returns:
        The final AgentState dict with keys: final_answer, active_agents,
        errors, generated_file_path, org_namespace.
    """
    initial_state: dict = {
        "query":         query,
        "org_namespace": org_namespace,
        "output_format": output_format,
    }
    if uploaded_file_path:
        initial_state["uploaded_file_path"] = uploaded_file_path

    result = manager_app.invoke(
        initial_state,
        config={"recursion_limit": recursion_limit},
    )
    # Surface the namespace so callers can log/audit which org was served
    result["org_namespace"] = org_namespace
    return result
