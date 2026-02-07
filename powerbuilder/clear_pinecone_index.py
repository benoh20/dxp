import os
from pinecone import Pinecone
from dotenv import load_dotenv

load_dotenv()

pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
index = pc.Index(os.getenv("OPENAI_PINECONE_INDEX_NAME"))

# This deletes everything in the __default__ namespace

print("Wiping __default__ namespace...")

# Make sure you're providing the correct namespace when you're wiping things!!
index.delete(delete_all=True, namespace = "__default__")

print ("Namespace cleared")

# works like a charm