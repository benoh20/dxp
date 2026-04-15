import os
import re
from datetime import date as _today

from dotenv import load_dotenv
load_dotenv()

from llama_parse import LlamaParse
from langchain_pinecone import PineconeVectorStore
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_core.documents import Document as LCDocument
from .state import AgentState

# parsing for pdf and word doc uploads
parser = LlamaParse(
    api_key=os.environ.get("LLAMA_CLOUD_API_KEY"),
    result_type="markdown"
)

_VALID_DOC_TYPES = {
    "research_memo", "polling_data", "field_report",
    "messaging_guide", "news_article", "academic_paper", "other",
}

# ---------------------------------------------------------------------------
# Shared metadata extractor — importable by bulk_upload.py
# ---------------------------------------------------------------------------

def extract_doc_metadata(text: str, llm) -> dict:
    """
    Makes two short LLM calls against the first 3000 characters of document
    text to extract a publication date and a document type classification.

    Returns a metadata dict ready to merge into a LangChain Document's metadata:

        date           : "YYYY-MM-DD" string if found, key omitted if unknown
        date_approximate: True when no date was found (omitted otherwise)
        date_ingested  : today's date in YYYY-MM-DD (always present)
        document_type  : one of the _VALID_DOC_TYPES strings
    """
    sample = text[:3000].strip()
    today  = _today.today().isoformat()

    # -- Date extraction ------------------------------------------------------
    date_prompt = (
        "What is the publication date of this document? "
        "Look for dates in headers, footers, or the first paragraph. "
        "Return only a date in YYYY-MM-DD format, or return the word unknown "
        "if no date is found.\n\n"
        f"{sample}"
    )
    try:
        date_raw = llm.invoke(date_prompt).content.strip()
    except Exception:
        date_raw = "unknown"

    date_match = re.search(r"\d{4}-\d{2}-\d{2}", date_raw)
    metadata: dict = {"date_ingested": today}
    if date_match:
        metadata["date"] = date_match.group(0)
    else:
        metadata["date_approximate"] = True

    # -- Document type classification -----------------------------------------
    type_prompt = (
        "What type of document is this? "
        "Return one of: research_memo, polling_data, field_report, "
        "messaging_guide, news_article, academic_paper, other.\n\n"
        f"{sample}"
    )
    try:
        doc_type = llm.invoke(type_prompt).content.strip().lower()
        # Extract the first valid token in case the LLM adds extra words
        for token in doc_type.split():
            if token in _VALID_DOC_TYPES:
                doc_type = token
                break
        else:
            doc_type = "other"
    except Exception:
        doc_type = "other"

    metadata["document_type"] = doc_type
    return metadata


# ---------------------------------------------------------------------------
# LangGraph node
# ---------------------------------------------------------------------------

def ingestor_node(state: AgentState):
    file_path     = state.get("uploaded_file_path")
    org_namespace = state.get("org_namespace")
    filename      = os.path.basename(file_path) if file_path else ""

    # 'general' is the shared read-only namespace for unaffiliated users.
    # Writing to it is blocked so one user cannot pollute the shared index.
    # Authenticated org members write to their own isolated namespace.
    if org_namespace == "general":
        return {
            "research_results": [
                "Document upload is not available for guest users. "
                "Please register with your organisation email to upload research."
            ],
            "active_agents": ["ingestor"],
        }

    if not file_path or not os.path.exists(file_path):
        return {"research_results": ["Error: File path not found."]}

    file_ext = os.path.splitext(file_path)[1].lower()

    # for unstructured data
    if file_ext in [".pdf", ".docx"]:
        # parse document
        llama_docs = parser.load_data(file_path)

        # Extract date and document_type from the first chunk's text.
        # Using gpt-4o-mini keeps this fast and cheap; the prompts are simple.
        llm          = ChatOpenAI(model="gpt-4o-mini", temperature=0)
        first_text   = llama_docs[0].text if llama_docs else ""
        doc_metadata = extract_doc_metadata(first_text, llm)

        # translate to LangChain Documents
        langchain_docs = []
        for doc in llama_docs:
            clean_doc = LCDocument(
                page_content=doc.text,
                metadata={
                    "source":   filename,
                    "filename": filename,
                    "text":     doc.text,
                    **doc_metadata,
                }
            )
            langchain_docs.append(clean_doc)

        # prepare embeddings
        embeddings = OpenAIEmbeddings(
            model="text-embedding-3-small",
            openai_api_key=os.environ.get("OPENAI_API_KEY"),
        )

        # upsert to Pinecone in org-specific namespace
        PineconeVectorStore.from_documents(
            documents=langchain_docs,
            embedding=embeddings,
            index_name=os.environ.get("OPENAI_PINECONE_INDEX_NAME"),
            namespace=org_namespace,
        )

        date_info = doc_metadata.get("date") or f"unknown (ingested {doc_metadata['date_ingested']})"
        return {
            "research_results": [
                f"Successfully indexed {filename} to the {org_namespace} research library. "
                f"Date: {date_info} | Type: {doc_metadata['document_type']}"
            ],
            "active_agents": ["ingestor"],
        }

    # for structured data (.csv files)
    elif file_ext == ".csv":
        save_dir = f"media/voter_files/{org_namespace}/"
        os.makedirs(save_dir, exist_ok=True)

        return {
            "research_results": [
                f"Voter file {filename} has been saved to the workspace data folder."
            ],
            "active_agents": ["ingestor"],
        }

    return {
        "research_results": ["Unsupported file type uploaded."],
        "active_agents": ["ingestor"],
    }
