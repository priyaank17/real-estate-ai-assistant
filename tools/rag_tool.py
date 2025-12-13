from typing import Any, Dict, List

from langchain_core.tools import tool

from helpers.vectorstore import get_vectorstore

MAX_RESULTS = 8


@tool
def search_rag(query: str) -> Dict[str, Any]:
    """
    Perform a semantic search over project descriptions and features.
    Returns structured matches with project IDs so the supervisor can shortlist and present them.
    
    Example: "projects with a sea view", "child friendly community", "near IT park"
    """
    try:
        vectorstore = get_vectorstore()
        results = vectorstore.similarity_search(query, k=MAX_RESULTS)

        if not results:
            return {
                "results": [],
                "project_ids": [],
                "preview_markdown": "",
                "message": "No relevant projects found matching the description.",
            }

        structured: List[Dict[str, Any]] = []
        for doc in results:
            meta = doc.metadata or {}
            project_id = str(meta.get("project_id") or meta.get("id") or "").strip() or None
            structured.append(
                {
                    "project_id": project_id,
                    "project_name": meta.get("project_name", "Unknown Project"),
                    "city": meta.get("city"),
                    "country": meta.get("country"),
                    "property_type": meta.get("property_type"),
                    "unit_type": meta.get("unit_type"),
                    "status": meta.get("status"),
                    "completion_date": meta.get("completion_date"),
                    "developer": meta.get("developer"),
                    "bedrooms": meta.get("bedrooms"),
                    "bathrooms": meta.get("bathrooms"),
                    "price": meta.get("price"),
                    "area": meta.get("area"),
                    "features": meta.get("features"),
                    "facilities": meta.get("facilities"),
                    "snippet": doc.page_content or "",
                    "description_chunk": doc.page_content or "",
                }
            )

        project_ids = [item["project_id"] for item in structured if item["project_id"]]
        return {
            "results": structured,
            "project_ids": project_ids,
            "preview_markdown": "",  # suppress table for RAG answers
            "source_tool": "search_rag",
        }
    except Exception as e:
        return {
            "error": f"Error performing semantic search: {str(e)}",
            "results": [],
            "project_ids": [],
            "preview_markdown": "",
        }
