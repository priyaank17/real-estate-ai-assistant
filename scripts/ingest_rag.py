import os
import sys
import time
import dotenv
import django
from langchain_core.documents import Document

# Text splitter import with fallback
try:
    from langchain.text_splitter import RecursiveCharacterTextSplitter
except ImportError:
    try:
        from langchain_text_splitters import RecursiveCharacterTextSplitter  # type: ignore
    except ImportError:
        class RecursiveCharacterTextSplitter:
            """Minimal fallback splitter if langchain splitters are unavailable."""
            def __init__(self, chunk_size=400, chunk_overlap=50, separators=None):
                self.chunk_size = chunk_size
                self.chunk_overlap = chunk_overlap
                self.separators = separators or ["\n\n", "\n", ". ", " "]

            def split_text(self, text: str):
                if not text:
                    return []
                # Simple character-based sliding window
                chunks = []
                step = max(1, self.chunk_size - self.chunk_overlap)
                for i in range(0, len(text), step):
                    chunk = text[i:i + self.chunk_size]
                    if chunk:
                        chunks.append(chunk)
                return chunks

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

    # Text splitter for descriptions (layout-aware not needed here; simple semantic chunks)
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=400,
        chunk_overlap=50,
        separators=["\n\n", "\n", ". ", " "],
    )

    documents = []
    for project in projects:
        # Normalize missing/blank names
        original_name = project.name or ""
        if not original_name.strip() or original_name.strip().lower() in ("nan", "none", "null"):
            project.name = "Project name not available"
            project.save(update_fields=["name"])

        # 3. Construct Content
        # We combine key fields to make the semantic search effective
        header = f"""
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
        """.strip()

        desc_text = (project.description or "").strip()
        project_id = str(project.id)
        
        # Create Document with rich metadata (so previews can show full rows).
        # Coerce Decimal fields to float/str for Chroma metadata compatibility.
        price_val = float(project.price) if project.price is not None else None
        area_val = float(project.area) if project.area is not None else None
        bathrooms_val = float(project.bathrooms) if project.bathrooms is not None else None
        metadata = {
            "project_id": project_id,
            "id": project_id,  # backward-compatible key
            "project_name": project.name,
            "city": project.city,
            "country": project.country,
            "property_type": project.property_type,
            "unit_type": project.unit_type,
            "status": project.status or project.completion_date,
            "completion_date": project.completion_date,
            "developer": project.developer,
            "bedrooms": project.bedrooms,
            "bathrooms": bathrooms_val,
            "price": price_val,
            "area": area_val,
            "features": project.features,
            "facilities": project.facilities,
        }

        # Header chunk (compact key facts)
        documents.append(Document(page_content=header, metadata=metadata))

        # Description chunks (split long text, same metadata)
        if desc_text:
            for chunk in splitter.split_text(desc_text):
                documents.append(Document(page_content=chunk, metadata=metadata))
    
    # 4. Add to ChromaDB
    print(f"🧠 Indexing {len(documents)} documents into ChromaDB (Azure/OpenAI embeddings)...")
    vectorstore = get_vectorstore()
    
    # Use small batches with retry/backoff to avoid connection drops
    # Default batch size tuned for Azure/OpenAI; override via INGEST_BATCH_SIZE env var if needed
    batch_size = int(os.getenv("INGEST_BATCH_SIZE", 500))
    max_retries = 3
    backoff_seconds = 2

    for i in range(0, len(documents), batch_size):
        batch = documents[i:i+batch_size]
        batch_no = i // batch_size + 1
        attempt = 0
        success = False
        while attempt < max_retries and not success:
            try:
                vectorstore.add_documents(batch)
                success = True
                print(f"   ✓ Indexed batch {batch_no}/{(len(documents)-1)//batch_size + 1} ({len(batch)} docs)")
            except Exception as e:
                attempt += 1
                print(f"   ⚠️  Error on batch {batch_no} (attempt {attempt}/{max_retries}): {str(e)}")
                if attempt < max_retries:
                    sleep_for = backoff_seconds * attempt
                    print(f"   ↻ Retrying batch {batch_no} after {sleep_for}s ...")
                    time.sleep(sleep_for)
        if not success:
            print(f"   ❌ Could not index batch {batch_no}, trying docs individually...")
            for doc in batch:
                try:
                    vectorstore.add_documents([doc])
                    print(f"      ✓ Indexed {doc.metadata.get('project_name', 'Unknown')}")
                except Exception as retry_e:
                    print(f"      ❌ Failed to index: {doc.metadata.get('project_name', 'Unknown')} ({retry_e})")
        
    print("✅ Ingestion Complete!")

if __name__ == "__main__":
    ingest_data()
