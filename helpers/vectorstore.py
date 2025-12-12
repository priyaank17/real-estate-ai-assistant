"""
ChromaDB vectorstore helper for RAG functionality.
Provides a singleton pattern for vectorstore instance.
"""
from langchain_chroma import Chroma
from langchain_openai import OpenAIEmbeddings

# Configuration
CHROMA_PATH = "chroma_rag"
COLLECTION_NAME = "project_descriptions"
EMBEDDING_MODEL = "text-embedding-3-small"  # OpenAI's efficient embedding model

def get_vectorstore():
    """
    Returns a configured Chroma vector store instance with OpenAI embeddings.
    
    This is used for semantic search over property descriptions.
    
    Returns:
        Chroma: Vector store instance with OpenAI embeddings
    """
    embeddings = OpenAIEmbeddings(model=EMBEDDING_MODEL)
    
    vectorstore = Chroma(
        collection_name=COLLECTION_NAME,
        embedding_function=embeddings,
        persist_directory=CHROMA_PATH,
    )
    
    return vectorstore


def get_embeddings():
    """
    Returns the OpenAI embeddings instance (for use in ingestion scripts).
    
    Returns:
        OpenAIEmbeddings: Configured embeddings instance
    """
    return OpenAIEmbeddings(model=EMBEDDING_MODEL)
