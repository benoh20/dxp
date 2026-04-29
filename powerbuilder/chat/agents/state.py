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
    output_format: Literal["markdown", "csv", "text", "docx", "xlsx"] # define target file type
    demographic_intent: Optional[str]  # set by intent_router via keyword scan; "a+b" for combined demographics
    language_intent: Optional[str]     # set by intent_router via keyword scan; ISO 639-1 code (e.g. "es", "en", "zh", "vi", "ko")
    plan_mode: Optional[Literal["auto", "mobilization", "persuasion"]]
    # Milestone L: strategic frame the user picked for this plan.
    #   "mobilization" = turn out existing supporters (cheaper per outcome per Wesleyan 2024 + TFC 2024)
    #   "persuasion"   = move undecided voters (longer scripts, higher per-outcome cost)
    #   "auto"         = no override; manager infers from the query (default behavior, equivalent to None)
    # Cascades into messaging tone, paid-media channel weighting, and CTA shape.

    # Milestone K: A/B scaffolding toggle. When True, the messaging agent
    # produces two variants (A and B) per eligible social-leaning format and
    # appends a sample-size math block sized for the campaign's audience.
    ab_test: Optional[bool]

    # -- File Handling --
    uploaded_file_path: Optional[str] # path to new file for ingesting

    # -- Streaming progress --
    # When set, agent nodes emit progress events to chat.progress for the
    # streaming view to consume. None for non-streaming runs (tests, CLI).
    run_id: Optional[str]

    # -- Final Output --
    final_answer: str
    generated_file_path: Optional[str]  # path to primary generated output file (DOCX for plans)
    generated_files: Optional[List[str]]  # all generated files; for plans this is [DOCX, CSV]

    # -- Observability --
    errors: Annotated[List[str], operator.add]        # non-fatal errors from any agent
    active_agents: Annotated[List[str], operator.add] # log of agents called this run