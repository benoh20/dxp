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

    # provide current context to loop
    res_len = len(state.get("research_results", []))
    data_len = len(state.get("structured_data", []))

    prompt = f"""
    You are a Senior Political Strategist and Advisor. Your job is to coordinate specialist agents to fulfill the user's request.
    Use all of the specialist agents necessary to answer the user's request, but be efficient and strategic in your choices. 
    Only choose the agents that are necessary to answer the question or compile the requested file.
    Here is the User's Request:
    "{state['query']}"
    and your specialist agents' current progress:
    {res_len} research memos collected, and {data_len} data points collected.

    Here are the specialist agents available:
    - RESEARCHER: Use this agent to gather qualitative insights, analysis, and context from unstructured data like documents, articles, and reports. This agent is best for deep research questions that require synthesis of information across multiple sources.
    - WIN_NUMBER: Use this agent to calculate the number of votes needed to win an election with 52% of the vote based on factors like district demographics, historical voting patterns, and turnout rates. This agent is best for questions specifically about electoral math and strategy. 
    - PRECINCTS: Use this agent to gather data and insights about specific precincts, such as voter demographics, past election results, and key issues. This agent is best for questions that require localized insights and data. This agent will produce .csv files that list target precincts based on the user's criteria.
    - ELECTION_RESULTS: Use this agent to gather data and insights about past election results, such as vote shares, turnout, and historical trends. This agent is best for questions that require analysis of past elections.
    - MESSAGING: Use this agent to develop persuasive voter mobilization or voter persuasion scripts and messages for phone calling, text messages, digital ads, or door knocking. This agent uses the best recommendations from research and polling data to craft compelling messages that will resonate with target voters.
    - COST_CALCULATOR: Use this agent to calculate the cost of different campaign strategies and tactics, such as canvassing, phone banking, digital advertising, and mailers. This agent is best for questions that require budgeting and resource allocation insights.

    Instructions:
    - If the user specifically requests a "Political Plan", you MUST call RESEARCHER, WIN_NUMBER, PRECINCTS, ELECTION_RESULTS, MESSAGING, and COST_CALCULATOR agents to create a comprehensive political plan that includes research insights, target precincts, win number calculations, messaging strategies, and cost estimates. In this case, your decision should be POLITICAL_PLAN and the output format should be MARKDOWN.
    - Look at the "current progress" provided above. If a plan is requested but no research is collected yet, your DECISION should be RESEARCHER. If research is done but no math is done, your DECISION should be WIN_NUMBER, and so on.
    - For a Political Plan, the FORMAT must be MARKDOWN.
    - If you have gathered all necessary info to answer the request fully, return 'FINISH'.
    - Otherwise, return the name of the NEXT specialist needed.

    Return your answer in this format: DECISION: [Specialist], FORMAT: [Format]
    """

    response = llm.invoke(prompt).content.upper()

    specialists = ["RESEARCHER"
    , "PRECINCTS"
    , "ELECTION_RESULTS"
    , "WIN_NUMBER"
    , "MESSAGING"
    , "COST_CALCULATOR"
    , "FINISH"]
    decision = next((s for s in specialists if s in response), "FINISH")

    formats = ["CSV", "MARKDOWN", "TEXT"]
    fmt = next((f for f in formats if f in response), "TEXT").lower()

    return {"router_decision": decision.lower(), "output_format": fmt}

# Create Synthesizer Node to compile results
def synthesizer_node(state: AgentState):

    text_context = "\n\n".join(state.get("research_results", []))
    table_context = str(state.get("structured_data", []))

    llm = get_model()

    prompt = f"""
    You are a Senior Political Strategist and Advisor.
    Using ONLY the provided documents, answer the user's request. 
    If you don't know the answer, say you don't know. Do not make up an answer.
    If you need more clarification to answer the question, or need more context 
    to know what kind of file or answer to provide, ask the user for more information.
    You should also ask the user what format they want the answer in (i.e. markdown, .csv, natural language) if it's not clear.

    Use this data to answer the query:
    Text Data:
    {text_context}
    Structured Data:
    {table_context}

    User Request:
    {state['query']}

    Output Format:
    {state['output_format']}

    Instructions:
    - Combine the data into a professional response. If the format is Markdown, use H1, H2, bold text, and tables. If the format is CSV, provide only the raw CSV data in comma-separated rows with a header row naming each column. If the format is text, provide a concise answer.
    - If the answer isn't available in the materials you have, say that you don't have the necessary information.
    - Use a professional and concise tone, but be conversational.
    - Cite the 'source' filename and document page number (if available). If there is no page number, quote the passage and cite the file name you're getting your answers from.

    """

    response = llm.invoke(prompt)

    return {"final_answer": response.content}
    pass

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
        "finish": "synthesizer" # this is the exit path
    }
)


# every agent points back to the intent_router to make sure the question is answered
workflow.add_edge("researcher", "intent_router")
# workflow.add_edge("precincts", "intent_router")
# workflow.add_edge("election_results", "intent_router")
# workflow.add_edge("win_number", "intent_router")
# workflow.add_edge("messaging", "intent_router")
# workflow.add_edge("cost_calculator", "intent_router")
# add other agents here

# Synthesizer goes to Export
workflow.add_edge("synthesizer", "export")
workflow.add_edge("export", END)

manager_app = workflow.compile()
