import os
from dotenv import load_dotenv
from llama_parse import LlamaParse
from pinecone import Pinecone # Added for the manual query check
from langchain_core.documents import Document as LCDocument
from langchain_pinecone import PineconeVectorStore
from langchain_openai import OpenAIEmbeddings

# Load variables from .env
load_dotenv()

def bulk_upsert(directory_path):
    # 1. Initialize Clients & Keys
    api_key = os.getenv("PINECONE_API_KEY")
    index_name = os.getenv("OPENAI_PINECONE_INDEX_NAME")
    
    # Initialize the raw Pinecone client for the existence check
    pc = Pinecone(api_key=api_key)
    index = pc.Index(index_name)
    
    embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
    parser = LlamaParse(result_type="markdown")

    # 2. Get list of files in the local folder
    files = [f for f in os.listdir(directory_path) if f.endswith('.pdf')]

    for filename in files:
        # 3. DE-DUPLICATION CHECK: Ask Pinecone if this filename exists
        # We use the raw index client here because it's faster for filtering
        existing_vectors = index.query(
            namespace="__default__",
            filter={"filename": {"$eq": filename}},
            top_k=1,
            vector=[0] * 1536  # Matches text-embedding-3-small dimensions
        )

        if len(existing_vectors['matches']) > 0:
            print(f"Skipping {filename}: Already indexed in Pinecone.")
            continue

        # 4. PARSING: Use LlamaParse to get clean Markdown nodes
        print(f"Processing new file: {filename}...")
        file_path = os.path.join(directory_path, filename)
        llama_docs = parser.load_data(file_path)

        # 5. CONVERSION: Flatten LlamaNodes into clean LangChain Documents
        langchain_docs = []
        for doc in llama_docs:
            clean_doc = LCDocument(
                page_content=doc.text, 
                metadata={
                    "source": filename,
                    "filename": filename, # Critical for the filter check above
                    "text": doc.text      # Ensures 'researcher.py' can find the text
                }
            )
            langchain_docs.append(clean_doc)

        # 6. UPSERT: Send the clean batch to Pinecone
        print(f"Upserting {len(langchain_docs)} chunks...")
        PineconeVectorStore.from_documents(
            langchain_docs, 
            embeddings, 
            index_name=index_name,
            namespace="__default__"
        )
        print(f"Successfully uploaded {filename}.")

if __name__ == "__main__":
    # Ensure this folder exists and has your PDFs in it
    bulk_upsert("./research_memos")