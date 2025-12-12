from langchain_core.tools import tool
from helpers.vectorstore import get_vectorstore

@tool
def search_rag(query: str) -> str:
    """
    Perform a semantic search over project descriptions and features.
    Useful for finding projects based on amenities, vibe, or specific text descriptions 
    that are not easily captured by structured SQL filters.
    
    Example: "projects with a sea view", "child friendly community", "near IT park"
    """
    try:
        vectorstore = get_vectorstore()
        # Retrieve top 5 matches
        results = vectorstore.similarity_search(query, k=5)
        
        if not results:
            return "No relevant projects found matching the description."
            
        formatted_results = []
        for doc in results:
            project_name = doc.metadata.get("project_name", "Unknown Project")
            content = doc.page_content
            formatted_results.append(f"Project: {project_name}\nDescription: {content}\n---")
            
        return "\n".join(formatted_results)
    except Exception as e:
        return f"Error performing semantic search: {str(e)}"
