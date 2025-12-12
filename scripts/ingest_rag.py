import os
import sys
import dotenv

# Load environment variables
dotenv.load_dotenv()
import django
from langchain_chroma import Chroma
from langchain_ollama import OllamaEmbeddings
from langchain_core.documents import Document

# 1. Setup Django
sys.path.append(os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'silver_land.settings')
django.setup()

from agents.models import Project
from helpers.vectorstore import get_vectorstore

def ingest_data():
    print("🚀 Starting RAG Ingestion (Ollama)...")
    
    # 2. Fetch Projects
    projects = Project.objects.all()
    print(f"📦 Found {projects.count()} projects in database.")
    
    if projects.count() == 0:
        print("⚠️ No projects found. Run seed_data.py first.")
        return

    documents = []
    for project in projects:
        # 3. Construct Content
        # We combine key fields to make the semantic search effective
        content = f"""
        Project Name: {project.name}
        Description: {project.description}
        Features: {project.features}
        Facilities: {project.facilities}
        City: {project.city}
        Property Type: {project.property_type}
        """
        
        # Clean up whitespace
        content = "\n".join([line.strip() for line in content.split("\n") if line.strip()])
        
        # Create Document with metadata
        doc = Document(
            page_content=content,
            metadata={
                "project_name": project.name,
                "city": project.city,
                "id": project.id
            }
        )
        documents.append(doc)
    
    # 4. Add to ChromaDB
    print(f"🧠 Indexing {len(documents)} documents into ChromaDB...")
    vectorstore = get_vectorstore()
    
    # Use smaller batches to avoid Ollama timeout/connection issues
    batch_size = 10  # Reduced from 100 to prevent Ollama EOF errors
    for i in range(0, len(documents), batch_size):
        batch = documents[i:i+batch_size]
        try:
            vectorstore.add_documents(batch)
            print(f"   ✓ Indexed batch {i//batch_size + 1}/{(len(documents)-1)//batch_size + 1} ({len(batch)} docs)")
        except Exception as e:
            print(f"   ⚠️  Error on batch {i//batch_size + 1}: {str(e)}")
            print(f"   Retrying with smaller batch...")
            # Retry with even smaller batch
            for doc in batch:
                try:
                    vectorstore.add_documents([doc])
                except Exception as retry_e:
                    print(f"   ❌ Failed to index: {doc.metadata.get('project_name', 'Unknown')}")
        
    print("✅ Ingestion Complete!")

if __name__ == "__main__":
    ingest_data()
