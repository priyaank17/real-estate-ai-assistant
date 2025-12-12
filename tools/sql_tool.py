from langchain_core.tools import tool
from helpers.vanna import get_vanna_client

@tool
def execute_sql_query(query: str) -> str:
    """
    Execute a natural language query against the property database using Text-to-SQL (Vanna AI).
    
    Examples:
    - "Find 2 bedroom apartments in Dubai"
    - "Show properties under 500000"
    - "List all villas"
    """
    try:
        # Get Vanna client (trained with OpenAI)
        vn = get_vanna_client()
        
        # Use Vanna to convert natural language to SQL
        sql = vn.generate_sql(query)
        
        if not sql:
            return "Could not generate SQL for the query."
            
        print(f"🔍 Generated SQL: {sql}")
        
        # Execute the SQL
        df = vn.run_sql(sql)
        
        if df is None or df.empty:
            return "No results found."
            
        # Format results as a string
        return df.to_markdown(index=False)
        
    except Exception as e:
        return f"Error executing SQL query: {str(e)}"
