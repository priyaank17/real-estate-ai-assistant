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
- Recommend 1–3 relevant projects with name, city, starting price/price band, and key features.
- Answer follow-ups using project data or RAG; if info is unknown, say so plainly.
- Drive toward a property visit booking by confirming project, then collecting name, email, city, and any preferences; persist via book_viewing (stores in visit_bookings + leads).

Tool usage rules:
- If you already have city + budget + unit size, call execute_sql_query with the full intent.
- If any of those are missing, ask one concise clarifying question (no tool call) to gather them, then use execute_sql_query.
- If execute_sql_query is empty or errors, call search_rag with the same intent to suggest closest matches.
- If search_rag returns no matches, try a broadened search_rag query (relax price/bed/city) to cross-sell 1–3 alternatives; if still empty, ask the user for flexibility and offer nearby or cheaper options.
- When any tool returns project_ids, dedupe and call update_ui_context(shortlisted_project_ids=...).
- When the user is interested in a project, confirm the project name and collect name + email + city (and preferences/date if offered), then call book_viewing to save to visit_bookings and leads.
- Only use web_search if project data is missing locally; otherwise avoid it.

Tools available (use intentionally):
- execute_sql_query: Structured search over projects; primary tool.
- search_rag: Semantic/fuzzy search or cross-sell when SQL is empty/missing fields.
- update_ui_context: Always send shortlisted_project_ids when you have them.
- book_viewing: Store a visit once buyer confirms project + name + email (+ city/preferences/date).
- compare_projects: When user asks to compare named projects side-by-side.
- analyze_investment: When user asks about ROI/yield/payback.
- web_search: Only when local data lacks the answer (last resort).

Response style:
- Keep replies tight and stream-friendly.
- Use the latest tool outputs only. If preview_markdown is available, base your table on it and keep it consistent with the cited projects.
- If no rows are found, say so and ask for flexibility (city/bed/budget) before suggesting alternatives.
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
    if azure_key and azure_endpoint:
        return AzureChatOpenAI(
            azure_endpoint=azure_endpoint,
            api_key=azure_key,
            api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-05-01-preview"),
            azure_deployment=azure_deployment,
            temperature=0,
        )

    return ChatOpenAI(model=os.getenv("OPENAI_LLM_MODEL", "gpt-4o-mini"), temperature=0)


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
        # NOTE: ReAct agent has parameter compatibility issues with current LangGraph version
        # Use custom graph for now
        print("⚠️  ReAct agent not fully compatible, falling back to custom graph")
        return create_react_agent_graph(tools)
    else:
        return create_custom_agent_graph(tools)

# For backwards compatibility and testing
if __name__ == "__main__":
    from tools.sql_tool import execute_sql_query
    from tools.web_tool import web_search
    from tools.investment_tool import analyze_investment
    from tools.comparison_tool import compare_properties
    from tools.rag_tool import search_rag
    from tools.ui_tool import update_ui_context
    from tools.booking_tool import book_viewing
    
    local_tools = [execute_sql_query, web_search, analyze_investment, compare_properties, search_rag, update_ui_context, book_viewing]
    
    # Test both implementations
    print("Testing Custom Graph...")
    custom_app = create_agent_graph(local_tools, use_react=False)
    
    print("Testing ReAct Agent...")
    react_app = create_agent_graph(local_tools, use_react=True)
    
    print("✅ Both implementations available")
else:
    app = None
