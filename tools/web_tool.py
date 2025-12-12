from langchain_core.tools import tool

@tool
def web_search(query: str):
    """
    Mock web search tool.
    In a real scenario, this would use Tavily, SerpAPI, or Bing Search API.
    """
    print(f"Searching web for: {query}")
    
    # Mock responses based on query content
    query_lower = query.lower()
    
    if "school" in query_lower:
        return "There are several top-rated schools nearby, including St. Mary's High School and International Public School, both within a 2km radius."
    
    if "hospital" in query_lower:
        return "City General Hospital is located 3km away, and there is a 24/7 clinic within the community."
        
    if "transport" in query_lower or "metro" in query_lower:
        return "The nearest metro station is 500m away, providing easy connectivity to the city center."
    
    return "I found some general information about the area. It is a developing neighborhood with good infrastructure and increasing property value."
