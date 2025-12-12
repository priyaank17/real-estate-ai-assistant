"""
Legacy Vanna (0.x) helper for Text-to-SQL tools.
Uses the legacy OpenAI_Chat + ChromaDB_VectorStore stack.
"""
import os
from functools import lru_cache
from openai import AzureOpenAI, OpenAI
from vanna.legacy.openai import OpenAI_Chat
from vanna.legacy.chromadb import ChromaDB_VectorStore
from django.conf import settings

CHROMA_VANNA_PATH = str(settings.BASE_DIR / "chroma_vanna")


class VannaLegacy(ChromaDB_VectorStore, OpenAI_Chat):
    """Legacy Vanna class for Text-to-SQL."""

    def __init__(self, config=None, client=None):
        ChromaDB_VectorStore.__init__(self, config=config)
        OpenAI_Chat.__init__(self, config=config, client=client)


@lru_cache(maxsize=1)
def get_vanna_client():
    """
    Returns an initialized legacy Vanna client.
    Prefers Azure OpenAI if AZURE_OPENAI_* are set; otherwise falls back to OpenAI.
    """
    azure_key = os.getenv("AZURE_OPENAI_API_KEY")
    azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
    azure_version = os.getenv("AZURE_OPENAI_API_VERSION", "2024-10-21")
    azure_deployment = os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT", "gpt-4o-mini")

    client = None
    model = None

    if azure_key and azure_endpoint:
        client = AzureOpenAI(
            api_key=azure_key,
            azure_endpoint=azure_endpoint,
            api_version=azure_version,
        )
        model = azure_deployment  # Azure uses deployment name as model
    else:
        openai_key = os.getenv("OPENAI_API_KEY")
        client = OpenAI(api_key=openai_key) if openai_key else OpenAI()
        model = os.getenv("OPENAI_LLM_MODEL", "gpt-4o-mini")

    config = {
        "model": model,
        "path": CHROMA_VANNA_PATH,
    }

    vn = VannaLegacy(config=config, client=client)
    db_path = str(settings.DATABASES["default"]["NAME"])
    vn.connect_to_sqlite(db_path)
    return vn
