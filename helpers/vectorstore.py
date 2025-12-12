"""
ChromaDB vectorstore helper for RAG functionality.
Provides a singleton pattern for vectorstore instance.
"""
import os

from langchain_chroma import Chroma
from langchain_openai import AzureOpenAIEmbeddings, OpenAIEmbeddings

# Configuration
CHROMA_PATH = "chroma_rag"
COLLECTION_NAME = "project_descriptions"
EMBEDDING_MODEL = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")


def _get_embeddings():
    """
    Returns an embeddings instance (prefers Azure OpenAI, falls back to OpenAI).
    """
    azure_key = os.getenv("AZURE_OPENAI_API_KEY")
    azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
    azure_deployment = os.getenv("AZURE_OPENAI_EMBED_DEPLOYMENT", "text-embedding-3-small")
    if azure_key and azure_endpoint:
        return AzureOpenAIEmbeddings(
            azure_endpoint=azure_endpoint,
            api_key=azure_key,
            api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-05-01-preview"),
            azure_deployment=azure_deployment,
            request_timeout=30,
        )

    return OpenAIEmbeddings(model=EMBEDDING_MODEL, request_timeout=30)


def get_vectorstore():
    """
    Returns a configured Chroma vector store instance with embeddings.
    
    This is used for semantic search over property descriptions.
    
    Returns:
        Chroma: Vector store instance with OpenAI/Azure embeddings
    """
    embeddings = _get_embeddings()

    vectorstore = Chroma(
        collection_name=COLLECTION_NAME,
        embedding_function=embeddings,
        persist_directory=CHROMA_PATH,
    )

    return vectorstore


def get_embeddings():
    """
    Returns the embeddings instance (for use in ingestion scripts).
    
    Returns:
        OpenAIEmbeddings | AzureOpenAIEmbeddings: Configured embeddings instance
    """
    return _get_embeddings()
