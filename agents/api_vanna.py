"""
Vanna 2.0 API Integration

Alternative API endpoint using Vanna 2.0 agent framework.
"""
from ninja import NinjaAPI, Schema
from ninja.responses import Response
from typing import Optional, Dict, Any
import uuid
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
        
        # Execute agent (simplified for Vanna 2.0 API)
        # Note: Actual execution will depend on Vanna's execute API
        # For now, return a basic response structure
        
        return {
            "response": f"Vanna 2.0 received: {payload.message}",
            "conversation_id": conversation_id,
            "metadata": {
                "user_id": user_id,
                "tools_available": ["run_sql", "investment", "comparison", "booking", "similarity"]
            }
        }
    except Exception as e:
        return Response(
            {"error": str(e)},
            status=500
        )


# Add CORS headers middleware
@api_vanna.api_controller("/", tags=["Root"])
class RootController:
    @api_vanna.get("/")
    def root(self, request):
        return {"message": "Vanna 2.0 API", "version": "2.0"}
