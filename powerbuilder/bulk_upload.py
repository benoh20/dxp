import os
from dotenv import load_dotenv
from llama_parse import LlamaParse
from langchain_core.documents import Document as LCDocument
from langchain_pinecone import PineconeVectorStore
from langchain_openai import OpenAIEmbeddings

load_dotenv()

def bulk_upsert(directory_path):
    # 1. Initialize Pinecone & Index
    pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
    index_name = os.getenv("OPENAI_PINECONE_INDEX_NAME")
    index = pc.Index(index_name)
    
    embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
    parser = LlamaParse(result_type="markdown")

    # 2. Get list of files in the folder
    files = [f for f in os.listdir(directory_path) if f.endswith('.pdf')]

    for filename in files:
        # 3. THE CHECK: Ask Pinecone if this file already exists in the 'general' namespace
        existing_vectors = index.query(
            namespace="__default__",
            filter={"filename": {"$eq": filename}},
            top_k=1, # We only need to find one to know it's there
            vector=[0] * 1536 # Dummy vector for a metadata-only search
        )

        if len(existing_vectors['matches']) > 0:
            print(f"Skipping {filename}: Already indexed.")
            continue

        # 4. If not found, proceed with parsing and upload
        print(f"Processing new file: {filename}...")
        file_path = os.path.join(directory_path, filename)
        docs = parser.load_data(file_path)

        # Add filename to metadata of every chunk
        for doc in docs:
            doc.metadata["filename"] = filename

        # Upsert to Pinecone
        PineconeVectorStore.from_documents(
            docs, 
            embeddings, 
            index_name=index_name,
            namespace="__default__"
        )
        print(f"Successfully uploaded {filename}.")

if __name__ == "__main__":
    bulk_upsert("./research_memos")