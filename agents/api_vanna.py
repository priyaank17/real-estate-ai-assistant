"""
Vanna 2.0 API Integration

Alternative API endpoint using Vanna 2.0 agent framework.
"""
from ninja import NinjaAPI, Schema
from typing import Optional, Dict, Any
import uuid
from vanna_agent import create_vanna_agent
from vanna.core.user import User

api_vanna = NinjaAPI(title="Silver Land Properties - Vanna 2.0 API", version="2.0")

# Initialize Vanna agent
vanna_agent = create_vanna_agent()
print("✅ Vanna 2.0 Agent initialized")


class ChatRequest(Schema):
    message: str
    conversation_id: Optional[str] = None
    user_id: Optional[str] = None


class ChatResponse(Schema):
    response: str
    conversation_id: str
    metadata: Optional[Dict[str, Any]] = None


@api_vanna.post("/chat", response=ChatResponse)
async def chat(request, payload: ChatRequest):
    """
    Chat with Vanna 2.0 agent.
    
    The agent has access to:
    - SQL queries (with Tool Memory for learning)
    - Investment analysis
    - Property comparison
    - Booking viewings
    """
    conversation_id = payload.conversation_id or str(uuid.uuid4())
    user_id = payload.user_id or "demo-user"
    
    # Create user context
    user = User(
        id=user_id,
        email=f"{user_id}@example.com",
        group_memberships=['user']
    )
    
    # Execute agent
    result = await vanna_agent.execute(
        messages=[{"role": "user", "content": payload.message}],
        user=user,
        conversation_id=conversation_id
    )
    
    return {
        "response": result.final_message or "No response generated.",
        "conversation_id": conversation_id,
        "metadata": {
            "tools_used": [step.tool_name for step in result.steps if hasattr(step, 'tool_name')],
            "user_id": user_id
        }
    }
