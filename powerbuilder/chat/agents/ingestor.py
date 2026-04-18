import os
import re
import shutil
from datetime import date as _today, datetime as _datetime, timezone as _tz

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

def extract_doc_metadata(text: str, llm, filename: str = "") -> dict:
    """
    Extracts a publication date and document type classification.

    Date extraction order:
      1. Regex scan of the filename for a 4-digit year (1990–2030) — free, instant.
         Sets date to "YYYY" and date_approximate: True. Skips the LLM date call.
      2. LLM call against the first 3000 chars of text — only when the filename
         yields no year.

    Returns a metadata dict ready to merge into a LangChain Document's metadata:

        date            : "YYYY-MM-DD" or "YYYY" string if found, omitted if unknown
        date_approximate: True when only a year (not a full date) was found,
                          or when no date was found at all (omitted otherwise)
        date_ingested   : today's date in YYYY-MM-DD (always present)
        document_type   : one of the _VALID_DOC_TYPES strings
    """
    sample = text[:3000].strip()
    today  = _today.today().isoformat()
    metadata: dict = {"date_ingested": today}

    # -- Date extraction: filename year scan first ----------------------------
    # Check the filename for a 4-digit year before making any LLM call.
    # Many documents embed the year in the filename (e.g. "polling_memo_2023.pdf").
    filename_year_match = re.search(r"\b(19[9]\d|20[0-2]\d|2030)\b", filename)
    if filename_year_match:
        metadata["date"]             = filename_year_match.group(0)  # "YYYY"
        metadata["date_approximate"] = True
    else:
        # -- Date extraction: LLM fallback ------------------------------------
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

    if not file_path or not os.path.exists(file_path):
        return {"research_results": ["Error: File path not found."],
                "active_agents": ["ingestor"]}

    file_ext = os.path.splitext(file_path)[1].lower()

    # ------------------------------------------------------------------
    # ROUTING DECISION — why these two paths are strictly separate:
    #
    # PDF / DOCX  →  LlamaParse → OpenAI embeddings → Pinecone
    #   Unstructured research documents become searchable vector chunks
    #   scoped to the org's Pinecone namespace.  Writing to Pinecone is
    #   restricted to authenticated org members (org_namespace != "general")
    #   to prevent guest users from polluting the shared index.
    #
    # CSV / XLSX  →  data/uploads/{timestamp}_{filename} → VoterFileAgent
    #   Structured voter files contain PII and must NEVER be sent to
    #   Pinecone.  They are copied to a stable local path so VoterFileAgent
    #   can read them reliably (Django's temp upload path may be cleaned up
    #   before the agent runs).  The file is discarded after analysis;
    #   nothing is written to the vector database.
    # ------------------------------------------------------------------

    if file_ext in (".pdf", ".docx"):
        # Pinecone writes are restricted to authenticated org namespaces.
        # 'general' is shared and read-only to prevent cross-org pollution.
        if org_namespace == "general":
            return {
                "research_results": [
                    "Document upload is not available for guest users. "
                    "Please register with your organisation email to upload research."
                ],
                "active_agents": ["ingestor"],
            }

        # Parse unstructured document
        llama_docs = parser.load_data(file_path)

        # Extract date and document_type from the first chunk's text.
        # Using gpt-4o-mini keeps this fast and cheap; the prompts are simple.
        llm          = ChatOpenAI(model="gpt-4o-mini", temperature=0)
        first_text   = llama_docs[0].text if llama_docs else ""
        doc_metadata = extract_doc_metadata(first_text, llm, filename=filename)

        langchain_docs = []
        for doc in llama_docs:
            langchain_docs.append(LCDocument(
                page_content=doc.text,
                metadata={
                    "source":   filename,
                    "filename": filename,
                    "text":     doc.text,
                    **doc_metadata,
                }
            ))

        embeddings = OpenAIEmbeddings(
            model="text-embedding-3-small",
            openai_api_key=os.environ.get("OPENAI_API_KEY"),
        )

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

    if file_ext in (".csv", ".xlsx", ".xls"):
        # Copy to a stable local path before handing off to VoterFileAgent.
        # Django's temp upload path is not guaranteed to survive until the
        # agent runs, so we persist the file ourselves with a timestamp prefix
        # to avoid collisions when the same filename is uploaded more than once.
        uploads_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "data", "uploads",
        )
        os.makedirs(uploads_dir, exist_ok=True)

        timestamp   = _datetime.now(_tz.utc).strftime("%Y%m%d_%H%M%S_%f")
        stable_name = f"{timestamp}_{filename}"
        stable_path = os.path.join(uploads_dir, stable_name)
        shutil.copy2(file_path, stable_path)

        return {
            "uploaded_file_path": stable_path,
            "research_results": [
                f"Voter file {filename} received. Routing to voter file analyst."
            ],
            "active_agents": ["ingestor"],
        }

    return {
        "research_results": ["Unsupported file type uploaded."],
        "active_agents": ["ingestor"],
    }
