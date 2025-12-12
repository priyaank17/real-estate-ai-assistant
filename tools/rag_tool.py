from typing import Any, Dict, List

from langchain_core.tools import tool

from helpers.vectorstore import get_vectorstore

MAX_RESULTS = 5


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
                    "property_type": meta.get("property_type"),
                    "snippet": doc.page_content[:400],
                }
            )

        project_ids = [item["project_id"] for item in structured if item["project_id"]]
        columns = ["project_id", "project_name", "city", "property_type", "snippet"]
        try:
            # Avoid heavy dependencies; build markdown manually
            header_line = "| " + " | ".join(columns) + " |"
            separator_line = "| " + " | ".join(["---"] * len(columns)) + " |"
            value_lines = []
            for item in structured:
                values = [
                    item.get("project_id") or "",
                    item.get("project_name") or "",
                    item.get("city") or "",
                    item.get("property_type") or "",
                    (item.get("snippet") or "")[:200].replace("\n", " "),
                ]
                value_lines.append("| " + " | ".join(values) + " |")
            preview_markdown = "\n".join([header_line, separator_line] + value_lines)
        except Exception:
            preview_markdown = ""

        return {
            "results": structured,
            "project_ids": project_ids,
            "preview_markdown": preview_markdown,
        }
    except Exception as e:
        return {
            "error": f"Error performing semantic search: {str(e)}",
            "results": [],
            "project_ids": [],
            "preview_markdown": "",
        }
