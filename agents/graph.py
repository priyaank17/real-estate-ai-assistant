import os
from typing import TypedDict, Annotated, List
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode, create_react_agent
from langgraph.checkpoint.memory import MemorySaver
from langchain_core.messages import BaseMessage, SystemMessage, HumanMessage
from langchain_openai import AzureChatOpenAI, ChatOpenAI
import operator

# Define State
class AgentState(TypedDict):
    messages: Annotated[List[BaseMessage], operator.add]

# System prompt (shared by both implementations)
SYSTEM_PROMPT = """You are a property concierge. Your goals:
- Greet new buyers and proactively collect location (city), budget range, and unit size (bedrooms) with minimal questions.
- Recommend 1–3 relevant projects with name, city, starting price/price band, and key features using tools provided only.
- Answer follow-ups using project data or RAG; if info is unknown, say so plainly.
- Drive toward a property visit booking by confirming project, then collecting name, email, city, and any preferences; persist via book_viewing (stores in visit_bookings + leads).
- Assume all prices in the database are USD. If the user supplies another currency (e.g., AED/INR/GBP), either clarify or convert to an approximate USD value before calling tools so filters are sensible.
Tool usage rules:
- If you already have city + budget + unit size, call execute_sql_query with the full intent.
- If you have any strong filter (city OR budget OR bedrooms OR property type OR developer/project name/amenity), still call execute_sql_query with the filters you have; and then call search rag as well and combine the results ,do not wait to gather every field.
- Call extract_intent_filters first to pull project/developer/city/price/bedrooms/property_type/features from the user message; use that to decide tools. If the user provides a specific developer, project name, amenity, or description-based intent, immediately call search_rag with that name/descriptor, and also call execute_sql_query with whatever filters are present (even if city/budget/bedrooms are missing). Do NOT ask for filters first in these cases.
- If key filters (city/bed/budget) are missing, still run search_rag with the partial intent to propose closest matches, and ask one concise clarifying question to gather the missing filters; when you obtain any filter, also call execute_sql_query.
- For questions about a known project/developer (units, amenities, proximity, offerings), call search_rag with that project/developer name first. If RAG is empty, try execute_sql_query with a developer LIKE '%name%' filter. Do not ask for filters first in these cases.
- If execute_sql_query is empty or errors, call search_rag with the same intent to suggest closest matches.
- If search_rag returns no matches, try a broadened search_rag query (relax price/bed/city) to cross-sell 1–3 alternatives; if still empty, ask the user for flexibility and offer nearby or cheaper options.
- Use search_rag for amenities/description questions about a named project when SQL lacks that detail.
- If execute_sql_query returns 0 rows, immediately call search_rag with the same intent (for fuzzy phrasing like "ready to move", "sea view", "near metro"). If both tools are empty, broaden search_rag to cross-sell 1–3 alternatives; if still nothing, say no exact matches and ask for flexibility (city/bed/budget).Mention which tools you tried.
- When any tool returns project_ids, dedupe and call update_ui_context(shortlisted_project_ids=...).
- When the user is interested in a project, confirm the project name and collect name + email + city (and preferences/date if offered), then call book_viewing to save to visit_bookings and leads.
- Only use web_search if project data is missing locally; otherwise avoid it.
- Never invent or reuse project names/cities that are not in the latest tool outputs. If no tool returned rows, explicitly say you could not find matching properties and ask for updated filters (city/bedrooms/budget).
- Do NOT recommend or describe any property that is not returned by a current tool call. If nothing matches, say so and ask for new filters.
- Do NOT mention tool names in the user-facing response; the UI shows tools_used separately.
- You may present a preview table if provided; keep markdown minimal if a table is shown. Do not fabricate tables; only use tool outputs.

Tools available (use intentionally):
- extract_intent_filters: Parse project/developer/city/price/bedrooms/property_type/features and a rewritten_query from the user message to ground tool calls.
- execute_sql_query: Structured search over projects; primary tool.
- search_rag: Semantic/fuzzy search or cross-sell when SQL is empty/missing fields or for amenity/description queries.
- update_ui_context: Always send shortlisted_project_ids when you have them.
- book_viewing: Store a visit once buyer confirms project + name + email (+ city/preferences/date).
- compare_projects: When user asks to compare named projects side-by-side.
- analyze_investment: When user asks about ROI/yield/payback.
- web_search: Only when local data lacks the answer (last resort).

Response style:
- Keep replies tight and stream-friendly.
- Use the latest tool outputs only. If preview_markdown is available, base your table on it and keep it consistent with the cited projects.
- If no rows are found, say you tried, ask for flexibility (city/bed/budget), and if possible offer 1–3 cross-sell alternatives from search_rag.
- Cite project names/cities from the current tool results; do not invent or reuse prior results.
- Do not hallucinate; if unsure or data is missing, state that.
"""

def _get_chat_model():
    """
    Prefer Azure OpenAI if configured; fallback to OpenAI.
    """
    azure_key = os.getenv("AZURE_OPENAI_API_KEY")
    azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
    azure_deployment = os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT", "gpt-4o-mini")
    temp = 0
    model_name = azure_deployment or os.getenv("OPENAI_LLM_MODEL", "gpt-4o-mini")
    if model_name and "nano" in model_name.lower():
        temp = 1  # some nano models only allow default temperature
    if azure_key and azure_endpoint:
        return AzureChatOpenAI(
            azure_endpoint=azure_endpoint,
            api_key=azure_key,
            api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-05-01-preview"),
            azure_deployment=azure_deployment,
            temperature=temp,
        )

    return ChatOpenAI(model=os.getenv("OPENAI_LLM_MODEL", "gpt-4o-mini"), temperature=temp)


def create_custom_agent_graph(tools: List):
    """
    Custom StateGraph implementation (manual control).
    
    Use this if you need:
    - Custom routing logic
    - Specific node behavior
    - Fine-grained control
    """
    model = _get_chat_model()
    model_with_tools = model.bind_tools(tools)
    
    def supervisor_node(state: AgentState):
        messages = state['messages']
        system_msg = SystemMessage(content=SYSTEM_PROMPT)
        response = model_with_tools.invoke([system_msg] + messages)
        return {"messages": [response]}
    
    def should_continue(state: AgentState):
        last_message = state['messages'][-1]
        if hasattr(last_message, 'tool_calls') and last_message.tool_calls:
            return "tools"
        return END
    
    workflow = StateGraph(AgentState)
    workflow.add_node("agent", supervisor_node)
    workflow.add_node("tools", ToolNode(tools))
    workflow.set_entry_point("agent")
    workflow.add_conditional_edges("agent", should_continue, {"tools": "tools", END: END})
    workflow.add_edge("tools", "agent")
    
    # Add memory
    memory = MemorySaver()
    return workflow.compile(checkpointer=memory)

def create_react_agent_graph(tools: List):
    """
    ReAct agent implementation (LangGraph built-in).
    
    Use this for:
    - Production (recommended)
    - Better reasoning loop
    - Standard agent pattern
    """
    model = _get_chat_model()
    memory = MemorySaver()
    
    # Create ReAct agent with state_modifier (not system_message)
    agent = create_react_agent(
        model=model,
        tools=tools,
        checkpointer=memory,
        state_modifier=SYSTEM_PROMPT  # Correct parameter name
    )
    
    return agent

def create_agent_graph(tools: List, use_react: bool = False):
    """
    Factory function - creates agent with tools and memory.
    
    Args:
        tools: List of LangChain tools
        use_react: If True, use ReAct agent. If False, use custom graph (default, more stable).
    
    Returns:
        Compiled agent with memory
    """
    if use_react:
        # Use custom graph for now
        print("⚠️  ReAct agent not fully compatible, falling back to custom graph")
        return create_react_agent_graph(tools)
    else:
        return create_custom_agent_graph(tools)

# For backwards compatibility and testing
if __name__ == "__main__":
    from tools.sql_tool import execute_sql_query
    from tools.intent_tool import extract_intent_filters
    from tools.web_tool import web_search
    from tools.investment_tool import analyze_investment
    from tools.comparison_tool import compare_properties
    from tools.rag_tool import search_rag
    from tools.ui_tool import update_ui_context
    from tools.booking_tool import book_viewing
    
    local_tools = [extract_intent_filters, execute_sql_query, web_search, analyze_investment, compare_properties, search_rag, update_ui_context, book_viewing]
    
    # Test both implementations
    print("Testing Custom Graph...")
    custom_app = create_agent_graph(local_tools, use_react=False)
    
    print("Testing ReAct Agent...")
    react_app = create_agent_graph(local_tools, use_react=True)
    
    print("✅ Both implementations available")
else:
    app = None
