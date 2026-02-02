from typing import Annotated, TypedDict, List
import operator

class AgentState(TypedDict):
    # The 'operator.add' tells LangGraph to append new results 
    # to the list rather than overwriting them.
    query: str
    research_results: Annotated[List[str], operator.add]
    election_data: Annotated[List[dict], operator.add]
    final_summary: str
    file_path: str  # To store the location of the generated Word document