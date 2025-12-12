"""
Vanna 2.0 API Integration

Alternative API endpoint using Vanna 2.0 agent framework.
"""
from ninja import NinjaAPI, Schema
from ninja.responses import Response
from typing import Optional, Dict, Any, List
import uuid
from vanna.core.user import User, RequestContext
from vanna.components.simple import SimpleComponentType, SimpleTextComponent
from vanna_agent import create_vanna_agent

# Create API
api_vanna = NinjaAPI(
    title="Silver Land Properties - Vanna 2.0 API",
    version="2.0"
)

# Initialize Vanna agent
vanna_agent = create_vanna_agent()
print("✅ Vanna 2.0 Agent initialized for API")



class ChatRequest(Schema):
    message: str
    conversation_id: Optional[str] = None
    user_id: Optional[str] = None


class ChatResponse(Schema):
    response: str
    conversation_id: str
    metadata: Optional[Dict[str, Any]] = None


@api_vanna.post("/vanna/chat", response=ChatResponse)
async def chat(request, payload: ChatRequest):
    """
    Chat with Vanna 2.0 agent.
    
    The agent has access to:
    - SQL queries (with Tool Memory for learning)
    - Investment analysis
    - Property comparison
    - Booking viewings
    """
    try:
        conversation_id = payload.conversation_id or str(uuid.uuid4())
        user_id = payload.user_id or "demo-user"

        # Build request context so SimpleUserResolver picks up user_id from headers
        ctx = RequestContext(headers={"X-User-ID": user_id})

        # Stream UI components and collect simple text responses
        texts: List[str] = []
        async for component in vanna_agent.send_message(
            request_context=ctx,
            message=payload.message,
            conversation_id=conversation_id,
        ):
            simple = getattr(component, "simple_component", None)
            if isinstance(simple, SimpleTextComponent):
                texts.append(simple.text)

        response_text = texts[-1] if texts else "No response."
        metadata = {"user_id": user_id, "tools_used": None}

        return {
            "response": response_text,
            "conversation_id": conversation_id,
            "metadata": metadata,
        }
    except Exception as e:
        return Response(
            {"error": str(e)},
            status=500
        )


# Root endpoint
@api_vanna.get("/")
def root(request):
    return {"message": "Vanna 2.0 API", "version": "2.0"}
