from ninja import NinjaAPI, Schema
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

# Create agent app with local tools and memory
agent_app = create_agent_graph(local_tools)
print("✅ API initialized with ReAct agent + memory")

class ChatRequest(Schema):
    message: str
    conversation_id: Optional[str] = None

class ChatResponse(Schema):
    response: str
    conversation_id: str
    data: Optional[Dict[str, Any]] = None

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
    for msg in reversed(result["messages"]):
        if msg.type == "ai" and hasattr(msg, 'tool_calls') and msg.tool_calls:
            for tool_call in msg.tool_calls:
                if tool_call["name"] == "update_ui_context":
                    structured_data = tool_call["args"]
                    break
            if structured_data:
                break
    
    return {
        "response": last_msg.content,
        "conversation_id": conversation_id,
        "data": structured_data if structured_data else None
    }
