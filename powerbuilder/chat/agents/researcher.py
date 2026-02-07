import os
import django
from langchain_openai import OpenAIEmbeddings
from langchain_pinecone import PineconeVectorStore
from .state import AgentState

# pointing to settings file with API Keys
os.environ.setdefault('DJANGO_SETTINGS_MODULE','powerbuilder_app.settings')

django.setup()

# pull in user query and domain
def research_node(state: AgentState):
    query = state["query"]
    org_namespace = state.get("org_namespace", "general")

    embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
    index_name = os.getenv("OPENAI_PINECONE_INDEX_NAME")

# Debugging 
    print(f"DEBUG: Searching Index '{index_name}' in Namespace '{org_namespace}'")

# search the general index for knowledge
    general_store = PineconeVectorStore(index_name=index_name, embedding=embeddings, namespace="__default__", text_key="text")
    general_docs = general_store.similarity_search(query, k=10)

# Debugging
    print(f"DEBUG: Found {len(general_docs)} documents in general namespace.")

# search the domain-specific index
    org_docs = []
    if org_namespace:
        org_store = PineconeVectorStore(index_name=index_name, embedding=embeddings, namespace=org_namespace)
        org_docs = org_store.similarity_search(query, k=10)

# Combine the general and domain index search results
    all_findings = [doc.page_content for doc in (general_docs + org_docs)]

    return {"research_results": all_findings}

# Local testing

if __name__ == "__main__":
    test_state = {"query": "What do young people care about?","org_namespace": "boh_key"}
    result = research_node(test_state)
    print(f"Retrieved {len(result['research_results'])} chunks.")