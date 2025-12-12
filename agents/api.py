from ninja import NinjaAPI, Schema
import json
from typing import List, Optional, Dict, Any
import uuid
from langchain_core.messages import HumanMessage
from agents.graph import create_agent_graph

# Import local tools
from tools.sql_tool import execute_sql_query
from tools.web_tool import web_search
from tools.investment_tool import analyze_investment
from tools.comparison_tool import compare_projects
from tools.rag_tool import search_rag
from tools.ui_tool import update_ui_context
from tools.booking_tool import book_viewing

api = NinjaAPI(title="Silver Land Properties Agent API")

# Initialize agent with local tools
local_tools = [
    execute_sql_query,
    web_search,
    analyze_investment,
    compare_projects,
    search_rag,
    update_ui_context,
    book_viewing
]

# Create agent app with local tools and memory (custom graph by default)
agent_app = create_agent_graph(local_tools)
print("✅ API initialized with custom agent graph + memory")

class ChatRequest(Schema):
    message: str
    conversation_id: Optional[str] = None

class ChatResponse(Schema):
    response: str
    conversation_id: str
    data: Optional[Dict[str, Any]] = None
    tools_used: Optional[List[str]] = None
    preview_markdown: Optional[str] = None
    citations: Optional[List[Dict[str, Any]]] = None

@api.post("/conversations")
def create_conversation(request):
    """
    Creates a new conversation session.
    """
    conv_id = str(uuid.uuid4())
    return {"conversation_id": conv_id}

@api.post("/agents/chat", response=ChatResponse)
async def chat(request, payload: ChatRequest):
    """
    Chat with the AI agent using local tools with conversation memory.
    """
    # Get or create conversation ID
    conversation_id = payload.conversation_id or str(uuid.uuid4())
    
    # Create config with thread_id for memory persistence
    # This allows the agent to remember previous messages in this conversation
    config = {"configurable": {"thread_id": conversation_id}}
    
    # Invoke the LangGraph agent with memory
    initial_state = {
        "messages": [HumanMessage(content=payload.message)]
    }
    
    result = await agent_app.ainvoke(initial_state, config=config)
    
    # Extract the last message (agent's response)
    last_msg = result["messages"][-1]
    
    # Extract structured data from tool calls
    structured_data = {}
    tools_used = []
    preview_markdown = None
    citations = None

    # Gather tools (preserve order of appearance)
    for msg in result["messages"]:
        if hasattr(msg, "tool_calls") and msg.tool_calls:
            for tool_call in msg.tool_calls:
                tool_name = tool_call.get("name")
                if tool_name:
                    tools_used.append(tool_name)
    # Capture latest tool outputs for previews/citations (reverse walk)
    for msg in reversed(result["messages"]):
        if getattr(msg, "type", None) == "tool":
            parsed = None
            if isinstance(msg.content, dict):
                parsed = msg.content
            elif isinstance(msg.content, str):
                try:
                    parsed = json.loads(msg.content)
                except Exception:
                    parsed = None
            if isinstance(parsed, dict):
                if parsed.get("preview_markdown") and not preview_markdown:
                    preview_markdown = parsed.get("preview_markdown")
                if parsed.get("results") and not citations:
                    citations = parsed.get("results")
            if preview_markdown and citations:
                break
    # Extract structured data from the latest update_ui_context call
    for msg in reversed(result["messages"]):
        if hasattr(msg, "tool_calls") and msg.tool_calls:
            for tool_call in msg.tool_calls:
                if tool_call.get("name") == "update_ui_context":
                    structured_data = tool_call.get("args", {})
                    break
            if structured_data:
                break
    
    # Deduplicate tools while preserving order
    seen = set()
    tools_used_deduped = []
    for t in tools_used:
        if t not in seen:
            tools_used_deduped.append(t)
            seen.add(t)
    
    return {
        "response": last_msg.content,
        "conversation_id": conversation_id,
        "data": structured_data if structured_data else None,
        "tools_used": tools_used_deduped if tools_used_deduped else None,
        "preview_markdown": preview_markdown,
        "citations": citations if citations else None,
    }
