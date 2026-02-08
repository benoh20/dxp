from typing import Annotated, TypedDict, List, Literal, Optional
import operator

class AgentState(TypedDict):
    """
    The 'Whiteboard' for the full application.
    Every node in our workflow reads from and writes to this dictionary.
    """

    # -- User Input and Context --
    query: str  # The user's original question or request
    org_namespace: str  # sanitized org ID for Pinecone multi-tenancy

    # -- Agent Findings --
    # the Annotated[] allows appending metadata together instead of replacing it
    research_results: Annotated[List[str], operator.add]

    # this part is for structured data (like Win Number or District Data)
    # this needs to be separate from the research_results"
    structured_data: Annotated[List[dict], operator.add]

    # -- Routing and Logic --
    router_decision: str # this holds the intent
    output_format: Literal["markdown", "csv", "text"] # define target file type

    # -- File Handling --
    uploaded_file_path: Optional[str] # path to new file for ingesting

    # -- Final Output --
    final_answer: str
    generated_file_path: str