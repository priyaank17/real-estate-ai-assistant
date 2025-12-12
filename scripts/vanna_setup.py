import os
import sys
import django
import pandas as pd
from vanna.openai import OpenAI_Chat
from vanna.chromadb import ChromaDB_VectorStore

# Setup Django
sys.path.append(os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'silver_land.settings')
django.setup()

from django.conf import settings
from agents.models import Project

# Vanna class using OpenAI
class VannaOpenAI(ChromaDB_VectorStore, OpenAI_Chat):
    def __init__(self, config=None):
        ChromaDB_VectorStore.__init__(self, config=config)
        OpenAI_Chat.__init__(self, config=config)

def setup_vanna():
    """
    Production-grade Vanna training for >90% accuracy using Ollama (Llama 3.1).
    Training components:
    1. DDL (Database Schema)
    2. Documentation (Column meanings, business rules)
    3. Question-SQL pairs (Diverse, real-world queries)
    """
    print("🚀 Starting Vanna Setup with Azure/OpenAI (GPT-4o-mini)...")
    
    config = {
        "model": os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT") or os.getenv("OPENAI_LLM_MODEL", "gpt-4o-mini"),
        "path": "chroma_vanna",
    }

    azure_key = os.getenv("AZURE_OPENAI_API_KEY")
    azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
    if azure_key and azure_endpoint:
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

    db_path = settings.DATABASES['default']['NAME']
    print(f"🔌 Connecting to SQLite DB at: {db_path}")
    vn.connect_to_sqlite(db_path)

    # ========================================
    # 1. Train on DDL (Schema)
    # ========================================
    print("\n🧠 Training on Database Schema (DDL)...")
    df_ddl = vn.run_sql("SELECT type, sql FROM sqlite_master WHERE sql is not null AND type='table'")
    for ddl in df_ddl['sql'].to_list():
        if 'agents_project' in ddl.lower():  # Focus on our main table
            vn.train(ddl=ddl)
            print(f"   ✓ Trained on DDL: {ddl[:80]}...")

    # ========================================
    # 2. Train on Documentation
    # ========================================
    print("\n📚 Training on Documentation...")
    
    # Column descriptions
    docs = [
        # Table Overview
        "The 'agents_project' table stores real estate project listings worldwide.",
        
        # Column Semantics
        "Column 'name': The project/property name (TEXT)",
        "Column 'bedrooms': Number of bedrooms (INTEGER). Can be 1, 2, 3, 4, 5+",
        "Column 'bathrooms': Number of bathrooms (INTEGER)",
        "Column 'property_type': Type of property - values are 'apartment', 'villa', 'townhouse' (lowercase)",
        "Column 'completion_status': Either 'off_plan' (under construction) or 'available' (ready to move)",
        "Column 'developer': Developer/builder company name (TEXT)",
        "Column 'price': Property price in USD (NUMERIC)",
        "Column 'area': Property area in square meters (NUMERIC)",
        "Column 'city': City location (TEXT) - e.g., 'Dubai', 'London', 'Chicago'",
        "Column 'country': Country code (TEXT) - e.g., 'US', 'AE', 'UK'",
        "Column 'completion_date': Completion date (DATE) in YYYY-MM-DD format",
        "Column 'features': JSON array of property features like ['pool', 'gym', 'parking']",
        "Column 'facilities': JSON array of building facilities",
        "Column 'description': Full text description of the project (TEXT)",
        
        # Business Rules
        "Price is always in USD, never in local currency",
        "Area is always in square meters, not square feet",
        "To search for features like 'pool' or 'gym', use LIKE '%pool%' on the features column",
        "To search for keywords in description, use LIKE '%keyword%' on description column",
        "completion_status='available' means ready to move in now",
        "completion_status='off_plan' means under construction",
        
        # Common Queries
        "Use WHERE city='Dubai' (case-sensitive) for Dubai properties",
        "Use WHERE property_type='villa' (lowercase) for villas",
        "For price range queries, use: price BETWEEN min AND max",
        "For bedroom count, use exact match: bedrooms = 2",
        "To find properties with specific developer: developer LIKE '%Developer Name%'",
    ]
    
    for doc in docs:
        vn.train(documentation=doc)
        print(f"   ✓ {doc[:60]}...")

    # ========================================
    # 3. Train on Question-SQL Pairs
    # ========================================
    print("\n💡 Training on Question-SQL Examples...")
    print("   (Using real column names and diverse query patterns)")
    
    training_queries = [
        # === BASIC FILTERS ===
        {
            "question": "Find 2 bedroom apartments in Dubai",
            "sql": "SELECT * FROM agents_project WHERE bedrooms = 2 AND property_type = 'apartment' AND city = 'Dubai'"
        },
        {
            "question": "Show me 3 bedroom villas under 1000000",
            "sql": "SELECT * FROM agents_project WHERE bedrooms = 3 AND property_type = 'villa' AND price < 1000000"
        },
        {
            "question": "List all townhouses",
            "sql": "SELECT * FROM agents_project WHERE property_type = 'townhouse'"
        },
        
        # === PRICE QUERIES ===
        {
            "question": "Properties under 500000",
            "sql": "SELECT * FROM agents_project WHERE price < 500000"
        },
        {
            "question": "Find properties between 1 million and 5 million",
            "sql": "SELECT * FROM agents_project WHERE price BETWEEN 1000000 AND 5000000"
        },
        {
            "question": "What is the average price of apartments?",
            "sql": "SELECT AVG(price) as average_price FROM agents_project WHERE property_type = 'apartment'"
        },
        
        # === LOCATION QUERIES ===
        {
            "question": "All properties in Dubai",
            "sql": "SELECT * FROM agents_project WHERE city = 'Dubai'"
        },
        {
            "question": "How many properties are in London?",
            "sql": "SELECT COUNT(*) as total FROM agents_project WHERE city = 'London'"
        },
        
        # === COMPLETION STATUS ===
        {
            "question": "Show me ready to move properties",
            "sql": "SELECT * FROM agents_project WHERE completion_status = 'available'"
        },
        {
            "question": "Find off plan projects",
            "sql": "SELECT * FROM agents_project WHERE completion_status = 'off_plan'"
        },
        
        # === COMBINATION QUERIES ===
        {
            "question": "2 bedroom apartments in Dubai under 800000",
            "sql": "SELECT * FROM agents_project WHERE bedrooms = 2 AND property_type = 'apartment' AND city = 'Dubai' AND price < 800000"
        },
        {
            "question": "Available 3 bedroom properties under 1.5 million",
            "sql": "SELECT * FROM agents_project WHERE bedrooms = 3 AND price < 1500000 AND completion_status = 'available'"
        },
        
        # === AGGREGATIONS ===
        {
            "question": "How many 2 bedroom apartments are available?",
            "sql": "SELECT COUNT(*) as total FROM agents_project WHERE bedrooms = 2 AND property_type = 'apartment'"
        },
        {
            "question": "Count properties by city",
            "sql": "SELECT city, COUNT(*) as total FROM agents_project GROUP BY city ORDER BY total DESC"
        },
        
        # === SORTING ===
        {
            "question": "Show cheapest apartments first",
            "sql": "SELECT * FROM agents_project WHERE property_type = 'apartment' ORDER BY price ASC"
        },
        {
            "question": "Top 10 most expensive properties",
            "sql": "SELECT * FROM agents_project ORDER BY price DESC LIMIT 10"
        },
    ]
    
    print(f"   Training on {len(training_queries)} question-SQL pairs...")
    for i, sample in enumerate(training_queries, 1):
        vn.train(question=sample["question"], sql=sample["sql"])
        if i % 5 == 0:
            print(f"   ✓ Trained {i}/{len(training_queries)} examples...")
    
    print(f"\n✅ Vanna Setup Complete!")
    print(f"   - Schema: Trained")
    print(f"   - Documentation: {len(docs)} entries")
    print(f"   - Query Examples: {len(training_queries)} pairs")
    print(f"\n⏱️  Estimated training time: ~1-2 minutes (local Ollama)")

if __name__ == "__main__":
    setup_vanna()
