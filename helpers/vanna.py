"""
Vanna client helper for Text-to-SQL functionality with OpenAI.
Provides a singleton pattern for Vanna instance.
"""
import os
from functools import lru_cache
import dotenv
from openai import OpenAI, AzureOpenAI
from vanna.openai import OpenAI_Chat
from vanna.chromadb import ChromaDB_VectorStore
from django.conf import settings

CHROMA_VANNA_PATH = str(settings.BASE_DIR / "chroma_vanna")

# Vanna class using OpenAI for LLM and ChromaDB for vector storage
class VannaOpenAI(ChromaDB_VectorStore, OpenAI_Chat):
    def __init__(self, config=None, client=None):
        ChromaDB_VectorStore.__init__(self, config=config)
        OpenAI_Chat.__init__(self, config=config, client=client)
        if not hasattr(self, "client") or self.client is None:
            # Fallback to default OpenAI client if not set
            from openai import OpenAI as _OpenAI
            self.client = client or _OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

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
    dotenv.load_dotenv()
    base_model = os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT") or os.getenv("OPENAI_LLM_MODEL", "gpt-4o-mini")
    config = {
        "model": base_model,
        "path": CHROMA_VANNA_PATH,  # Shared with scripts/vanna_setup.py
    }
    # Some models (e.g., gpt-nano) only support default temperature=1
    if base_model and "nano" in base_model.lower():
        config["temperature"] = 1.0

    azure_key = os.getenv("AZURE_OPENAI_API_KEY")
    azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
    openai_key = os.getenv("OPENAI_API_KEY")

    # Build client explicitly; avoid putting api_base/api_type in config (deprecated in vanna)
    client = None
    if azure_key and azure_endpoint:
        client = AzureOpenAI(
            api_key=azure_key,
            api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-05-01-preview"),
            azure_endpoint=azure_endpoint,
        )
    elif openai_key:
        client = OpenAI(api_key=openai_key)

    vn = VannaOpenAI(config=config, client=client)
    
    # Connect to Django's SQLite database
    db_path = str(settings.DATABASES["default"]["NAME"])
    vn.connect_to_sqlite(db_path)
    
    return vn
