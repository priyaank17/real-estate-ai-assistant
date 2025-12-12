import os
import sys
import dotenv
import django
from langchain_core.documents import Document

# 1. Setup Django
sys.path.append(os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'silver_land.settings')
django.setup()

from agents.models import Project
from helpers.vectorstore import get_vectorstore

def ingest_data():
    dotenv.load_dotenv()
    print("🚀 Starting RAG ingestion with Azure/OpenAI embeddings...")
    
    has_azure = bool(os.getenv("AZURE_OPENAI_API_KEY") and os.getenv("AZURE_OPENAI_ENDPOINT"))
    has_openai = bool(os.getenv("OPENAI_API_KEY"))
    if not (has_azure or has_openai):
        print("⚠️  No Azure or OpenAI credentials found. Set AZURE_OPENAI_API_KEY/AZURE_OPENAI_ENDPOINT or OPENAI_API_KEY.")
        return
    
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
        City: {project.city}
        Country: {project.country}
        Property Type: {project.property_type}
        Bedrooms: {project.bedrooms}
        Bathrooms: {project.bathrooms}
        Price: {project.price}
        Area: {project.area}
        Completion Status: {project.status or project.completion_date}
        Features: {project.features}
        Facilities: {project.facilities}
        Description: {project.description}
        """
        
        # Clean up whitespace
        content = "\n".join([line.strip() for line in content.split("\n") if line.strip()])
        project_id = str(project.id)
        
        # Create Document with metadata
        doc = Document(
            page_content=content,
            metadata={
                "project_name": project.name,
                "city": project.city,
                "property_type": project.property_type,
                "project_id": project_id,
                "id": project_id,  # backward-compatible key
            }
        )
        documents.append(doc)
    
    # 4. Add to ChromaDB
    print(f"🧠 Indexing {len(documents)} documents into ChromaDB (Azure/OpenAI embeddings)...")
    vectorstore = get_vectorstore()
    
    # Use modest batches to avoid API timeouts
    batch_size = 25
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
