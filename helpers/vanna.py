"""
Vanna client helper for Text-to-SQL functionality with OpenAI.
Provides a singleton pattern for Vanna instance.
"""
import os
from vanna.openai import OpenAI_Chat
from vanna.chromadb import ChromaDB_VectorStore
from django.conf import settings

# Vanna class using OpenAI for LLM and ChromaDB for vector storage
class VannaOpenAI(ChromaDB_VectorStore, OpenAI_Chat):
    def __init__(self, config=None):
        ChromaDB_VectorStore.__init__(self, config=config)
        OpenAI_Chat.__init__(self, config=config)

def get_vanna_client():
    """
    Returns an initialized Vanna client using OpenAI (GPT-4o-mini).
    
    This uses:
    - OpenAI GPT-4o-mini for SQL generation (fast & cheap)
    - ChromaDB for storing training data (DDL, docs, SQL examples)
    
    Returns:
        VannaOpenAI: Configured Vanna instance
    """
    vn = VannaOpenAI(config={
        'model': 'gpt-4o-mini',  # Cheapest, fastest OpenAI model
        'path': 'chroma_vanna'   # ChromaDB storage path
    })
    
    # Connect to Django's SQLite database
    db_path = settings.DATABASES['default']['NAME']
    vn.connect_to_sqlite(db_path)
    
    return vn

