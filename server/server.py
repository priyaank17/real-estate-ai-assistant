from mcp.server.fastmcp import FastMCP
import os
import sys
import django

# Setup Django environment for MCP server
sys.path.append('/Users/priyankjha/Desktop/real-estate-ai-assistant')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'silver_land.settings')
django.setup()

from agents.graph import app as agent_app
from agents.tools.investment_tool import analyze_investment
from agents.tools.comparison_tool import compare_projects

mcp = FastMCP("Silver Land Agent")

from langchain_core.messages import HumanMessage

@mcp.tool()
def ask_silver_land_agent(query: str) -> str:
    """
    Ask the Silver Land Properties AI assistant a question about properties, 
    bookings, or general inquiries. This uses the full agentic workflow.
    """
    initial_state = {
        "messages": [HumanMessage(content=query)],
        "conversation_id": "mcp-session",
    }
    
    result = agent_app.invoke(initial_state)
    # Extract final response from the last message
    last_msg = result["messages"][-1]
    return last_msg.content

from agents.tools.investment_tool import analyze_investment
from agents.tools.comparison_tool import compare_projects

from tools.sql_tool import execute_sql_query
from tools.web_tool import web_search
from tools.rag_tool import search_rag
from tools.booking_tool import book_viewing

@mcp.tool()
def query_database(query: str) -> str:
    """
    Execute a natural language query against the property database.
    Example: "Find 2 bedroom apartments in Dubai"
    """
    # Since execute_sql_query is a LangChain tool, we use invoke
    return execute_sql_query.invoke(query)

@mcp.tool()
def search_rag(query: str) -> str:
    """
    Perform a semantic search over project descriptions.
    Example: "projects with sea view", "child friendly"
    """
    return search_rag.invoke(query)

@mcp.tool()
def search_web(query: str) -> str:
    """
    Search the web for general information.
    Example: "Schools near Silver Heights"
    """
    return web_search.invoke(query)

@mcp.tool()
def get_investment_analysis(project_name: str) -> str:
    """
    Get a direct investment analysis for a specific project. 
    Returns ROI, Yield, and Score.
    """
    # analyze_investment is now a LangChain tool
    result = analyze_investment.invoke(project_name)
    if isinstance(result, dict):
        return f"Score: {result['investment_score']} | Yield: {result['rental_yield']} | Verdict: {result['verdict']}"
    return str(result)

@mcp.tool()
def compare_properties(project_names: list[str]) -> str:
    """
    Compare multiple properties side-by-side.
    Args:
        project_names: List of project names to compare.
    """
    # compare_projects is now a LangChain tool
    return compare_projects.invoke(project_names)

@mcp.tool()
def book_property_viewing(project_id: int, customer_name: str, customer_email: str, preferred_date: str) -> str:
    """
    Book a property viewing for a customer.
    Args:
        project_id: The ID of the project to view
        customer_name: Customer's full name
        customer_email: Customer's email address 
        preferred_date: Preferred viewing date in YYYY-MM-DD format
    """
    return book_viewing.invoke({
        "project_id": project_id,
        "customer_name": customer_name,
        "customer_email": customer_email,
        "preferred_date": preferred_date
    })

if __name__ == "__main__":
    mcp.run()
