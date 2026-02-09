import os
from llama_parse import LlamaParse
from langchain_pinecone import PineconeVectorStore
from langchain_openai import OpenAIEmbeddings
from langchain_core.documents import Document as LCDocument
from .state import AgentState

# parsing for pdf and word doc uploads
parser = LlamaParse(
    api_key=os.environ.get("LLAMA_CLOUD_API_KEY"),
    result_type = "markdown"
)

def ingestor_node(state: AgentState):
    file_path = state.get("uploaded_file_path")
    org_namespace = state.get("org_namespace")
    filename = os.path.basename(file_path)

    if not file_path or not os.path.exists(file_path):
        return {"research_results": ["Error: File path not found."]}
    
    file_ext = os.path.splitext(file_path)[1].lower()

    # for unstructured data
    if file_ext in [".pdf", ".docx"]:
        # parse document
        llama_docs = parser.load_data(file_path)

        # translate to LangChain Documents
        langchain_docs = []
        for doc in llama_docs:
            clean_doc = LCDocument(
                page_content=doc.text,
                metadata={
                    "source": filename,
                    "filename": filename,
                    "text": doc.text
                }
            )
            langchain_docs.append(clean_doc)

        # prepare embeddings
        embeddings = OpenAIEmbeddings(
            model="text-embedding-3-small"
            , openai_api_key=os.environ.get("OPENAI_API_KEY")
            )

        # upsert to Pinecone in org-specific namespace
        vectorstore = PineconeVectorStore.from_documents(
            documents=langchain_docs,
            embedding=embeddings,
            index_name=os.environ.get("OPENAI_PINECONE_INDEX_NAME"),
            namespace=org_namespace
        )

        return {"research_results": [f"Successfully indexed {os.path.basename(file_path)} to the {org_namespace} research library."]}
    
    # for structured data (.csv files)
    elif file_ext == ".csv":
        # might want to move this into a SQL database or Pandas storage later
        save_dir = f"media/voter_files/{org_namespace}/"
        os.makedirs(save_dir, exist_ok=True)
        
        return {"research_results": [f"Voter file {os.path.basename(file_path)} has been saved to the workspace data folder."]}
    
    return {"research_results": ["Unsupported file type uploaded."]}