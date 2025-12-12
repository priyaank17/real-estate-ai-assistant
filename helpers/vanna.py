"""
Vanna client helper for Text-to-SQL functionality with OpenAI.
Provides a singleton pattern for Vanna instance.
"""
import os
from functools import lru_cache
from vanna.openai import OpenAI_Chat
from vanna.chromadb import ChromaDB_VectorStore
from django.conf import settings

CHROMA_VANNA_PATH = str(settings.BASE_DIR / "chroma_vanna")

# Vanna class using OpenAI for LLM and ChromaDB for vector storage
class VannaOpenAI(ChromaDB_VectorStore, OpenAI_Chat):
    def __init__(self, config=None):
        ChromaDB_VectorStore.__init__(self, config=config)
        OpenAI_Chat.__init__(self, config=config)

@lru_cache(maxsize=1)
def get_vanna_client():
    """
    Returns an initialized Vanna client using OpenAI (GPT-4o-mini).
    
    This uses:
    - OpenAI GPT-4o-mini for SQL generation (fast & cheap)
    - ChromaDB for storing training data (DDL, docs, SQL examples)
    
    Returns:
        VannaOpenAI: Configured Vanna instance
    """
    config = {
        "model": os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT") or os.getenv("OPENAI_LLM_MODEL", "gpt-4o-mini"),
        "path": CHROMA_VANNA_PATH,  # Shared with scripts/vanna_setup.py
    }

    azure_key = os.getenv("AZURE_OPENAI_API_KEY")
    azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
    if azure_key and azure_endpoint:
        # Azure OpenAI configuration
        config.update(
            {
                "api_key": azure_key,
                "api_base": azure_endpoint,
                "api_type": "azure",
                "api_version": os.getenv("AZURE_OPENAI_API_VERSION", "2024-05-01-preview"),
                "deployment_id": os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT", "gpt-4o-mini"),
            }
        )
    else:
        api_key = os.getenv("OPENAI_API_KEY")
        if api_key:
            config["api_key"] = api_key

    vn = VannaOpenAI(config=config)
    
    # Connect to Django's SQLite database
    db_path = str(settings.DATABASES["default"]["NAME"])
    vn.connect_to_sqlite(db_path)
    
    return vn
