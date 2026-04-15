import os

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


# Define LLM and temperature for workflow
def get_model():
    return get_completion_client(temperature=0.3)

# Check if a file needs to be ingested first
def triage_router(state: AgentState):
    if state.get("uploaded_file_path"):
        return "ingestor"
    return "intent_router"

# Intent Router / Classification
def intent_router_node(state: AgentState):
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
    - MESSAGING: Generates canvassing scripts, text messages, mail narratives, and digital ad copy grounded in research.
    - COST_CALCULATOR: Estimates cost of campaign tactics (canvassing, phone banking, digital ads, mailers).
    - FINISH: All needed agents have run — proceed to final synthesis.

    DECISION RULES:

    1. POLITICAL PLAN REQUEST: If the user is asking for a political plan, program plan, or comprehensive campaign strategy, you must run agents in this exact order, returning the single next agent that has NOT yet appeared in the "Agents already completed" list:
       Step 1 → RESEARCHER
       Step 2 → ELECTION_RESULTS
       Step 3 → WIN_NUMBER
       Step 4 → PRECINCTS
       Step 5 → MESSAGING
       Step 6 → COST_CALCULATOR
       Step 7 → FINISH
       FORMAT: MARKDOWN

    2. SINGLE-TOPIC REQUEST: If the user asks a focused question, return only the single most relevant specialist. If you already have enough information to answer, return FINISH.

    IMPORTANT: Never return an agent that already appears in "Agents already completed."

    Return ONLY this line: DECISION: [specialist name], FORMAT: [markdown|csv|text]
    """

    response = llm.invoke(prompt).content.upper()

    # Order matters: longer/more specific strings must come before substrings.
    specialists = [
        "ELECTION_RESULTS",
        "COST_CALCULATOR",
        "WIN_NUMBER",
        "RESEARCHER",
        "PRECINCTS",
        "MESSAGING",
        "FINISH",
    ]
    decision = next((s for s in specialists if s in response), "FINISH")

    formats = ["CSV", "MARKDOWN", "TEXT"]
    fmt = next((f for f in formats if f in response), "TEXT").lower()

    return {"router_decision": decision.lower(), "output_format": fmt}

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
        "election_results": "election_results",
        "finish":           "synthesizer",
    }
)


# Every agent loops back to intent_router so the orchestrator can decide the next step
workflow.add_edge("researcher",    "intent_router")
workflow.add_edge("precincts",     "intent_router")
workflow.add_edge("win_number",    "intent_router")
workflow.add_edge("messaging",        "intent_router")
workflow.add_edge("cost_calculator",  "intent_router")
workflow.add_edge("election_results", "intent_router")

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
