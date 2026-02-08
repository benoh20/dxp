import os
from langgraph.graph import StateGraph, END
from .state import AgentState
from .researcher import research_node
from langchain_openai import ChatOpenAI

# YOU NEED TO IMPORT NEW AGENTS AS THEY GET BUILT
# from .precincts import precincts_node
# from .election_results import elections_node
# from .win_number import win_number_node
# from .messaging import messaging_node
# from .cost_calculator import cost_node
# from .ingestor import ingestor_node
# from .export import export_node


# Define LLM and temperature for workflow
def get_model():
    return ChatOpenAI(model="gpt-4o"
                      , temperature=0.3
                      , openai_api_key=os.environ["OPENAI_API_KEY"])

# Check if a file needs to be ingested first
def triage_router(state: AgentState):
    if state.get("uploaded_file_path"):
        return "ingestor"
    return "intent_router"

# Intent Router / Classification
def intent_router_node(state: AgentState):
    llm = get_model()

    prompt = f"""
    Analyze this user request, where the user is a staff member at a political organization looking for guidance:
    "{state['query']}"

    1. Which specialist is needed? (RESEARCHER
    , PRECINCTS
    , ELECTION_RESULTS
    , WIN_NUMBER
    , MESSAGING
    , COST_CALCULATOR)
    2. What is the best output format? (markdown, csv, text)

    Return your answer in this format: DECISION: [Specialist], FORMAT: [Format]
    """

    response = llm.invoke(prompt).content.upper()

    specialists = ["RESEARCHER"
    , "PRECINCTS"
    , "ELECTION_RESULTS"
    , "WIN_NUMBER"
    , "MESSAGING"
    , "COST_CALCULATOR"]
    decision = next((s for s in specialists if s in response), "RESEARCHER")

    formats = ["CSV", "MARKDOWN", "TEXT"]
    fmt = next((f for f in formats if f in response), "TEXT").lower()

    return {"router_decision": decision.lower(), "output_format": fmt}

# Create Synthesizer Node to compile results
def synthesizer_node(state: AgentState):

    text_context = "\n\n".join(state.get("research_results", []))
    table_context = str(state.get("structured_data", []))

    prompt = f"""
    You are a Senior Political Strategist and Advisor.
    Using ONLY the provided documents, answer the user's request. 
    If you don't know the answer, say you don't know. Do not make up an answer.
    If you need more clarification to answer the question, or need more context 
    to know what kind of file or answer to provide, ask the user for more information.
    You should also ask the user what format they want the answer in (i.e. markdown, .csv, natural language) if it's not clear.

    Text Data:
    {text_context}
    Structured Data:
    {table_context}

    User Request:
    {state['query']}

    Instructions:
    - Combine the data into a professional response. If the format is Markdown, use headers and tables. If the format is CSV, provide only the raw CSV data with a header row naming each column. If the format is text, provide a concise answer.
    - If the answer isn't available in the materials you have, say that you don't have the necessary information.
    - Use a professional and concise tone, but be conversational.
    - Cite the 'source' filename and document page number (if available). If there is no page number, quote the passage and cite the file name you're getting your answers from.

    """

    llm = get_model()

    response = llm.invoke(prompt)

    return {"final_answer": response.content}

# Constructing workflow for user request
workflow = StateGraph(AgentState)

# adding in all agents here
workflow.add_node("triage_router", lambda state: state)
workflow.add_node("intent_router", intent_router_node)
workflow.add_node("researcher", research_node)
workflow.add_node("synthesizer", synthesizer_node)

# workflow.add_node("election_results",elections_node)
# workflow.add_node("precincts", precincts_node)
# workflow.add_node("win_number", win_number_node)
# workflow.add_node("messaging", messaging_node)
# workflow.add_node("cost_calculator", cost_node)
# workflow.add_node("ingestor", ingestor_node)
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
        "researcher": "researcher",
        # "precincts": "precincts",
        # "election_results": "election_results",
        # "win_number": "win_number",
        # "messaging": "messaging",
        # "cost_calculator": "cost_calculator"
    }
)

workflow.add_edge("researcher", "synthesizer")
# workflow.add_edge("precincts", "synthesizer")
# workflow.add_edge("election_results", "synthesizer")
# workflow.add_edge("win_number", "synthesizer")
# workflow.add_edge("messaging", "synthesizer")
# workflow.add_edge("cost_calculator", "synthesizer")
# add other agents here

# Synthesizer goes to Export
workflow.add_edge("synthesizer", "export")
workflow.add_edge("export", END)

manager_app = workflow.compile()
