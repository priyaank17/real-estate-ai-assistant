from ninja import NinjaAPI, Schema
import json
from typing import List, Optional, Dict, Any
import uuid
import asyncio
from langgraph.errors import GraphRecursionError
from django.http import StreamingHttpResponse
from langchain_core.messages import HumanMessage
from agents.graph import create_agent_graph

# Import local tools
from tools.sql_tool import execute_sql_query
from tools.web_tool import web_search
from tools.intent_tool import extract_intent_filters
from tools.investment_tool import analyze_investment
from tools.comparison_tool import compare_projects
from tools.rag_tool import search_rag
from tools.ui_tool import update_ui_context
from tools.booking_tool import book_viewing

api = NinjaAPI(title="Silver Land Properties Agent API")

# Initialize agent with local tools
local_tools = [
    extract_intent_filters,
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

def _extract_structured(result: Dict[str, Any]):
    last_msg = result["messages"][-1]
    structured_data = {}
    tools_used = []
    preview_markdown = None
    citations = None

    # Only consider messages since the last human message
    messages = result["messages"]
    start_idx = len(messages) - 1
    for idx in range(len(messages) - 1, -1, -1):
        if getattr(messages[idx], "type", None) == "human":
            start_idx = idx + 1
            break
    current_turn = messages[start_idx:]

    for msg in current_turn:
        if getattr(msg, "type", None) == "tool":
            name = getattr(msg, "name", None) or getattr(msg, "tool_call", {}).get("name") if hasattr(msg, "tool_call") else None
            if name:
                tools_used.append(name)
        if hasattr(msg, "tool_calls") and msg.tool_calls:
            for tc in msg.tool_calls:
                tool_name = tc.get("name")
                if tool_name:
                    tools_used.append(tool_name)

    sql_preview = None
    fallback_preview = None
    for msg in reversed(current_turn):
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
                if parsed.get("preview_markdown"):
                    if parsed.get("source_tool") == "execute_sql_query" and not sql_preview:
                        sql_preview = parsed.get("preview_markdown")
                    elif not fallback_preview:
                        fallback_preview = parsed.get("preview_markdown")
                if parsed.get("results") and not citations:
                    filtered = []
                    for item in parsed.get("results", []):
                        name = item.get("project_name")
                        if name in (None, "", "nan"):
                            continue
                        filtered.append(item)
                    if filtered:
                        citations = filtered
            if (sql_preview or fallback_preview) and citations:
                break
    preview_markdown = sql_preview or fallback_preview

    for msg in reversed(current_turn):
        if hasattr(msg, "tool_calls") and msg.tool_calls:
            for tool_call in msg.tool_calls:
                if tool_call.get("name") == "update_ui_context":
                    structured_data = tool_call.get("args", {})
                    break
            if structured_data:
                break

    seen = set()
    tools_used_deduped = []
    for t in tools_used:
        if t not in seen:
            tools_used_deduped.append(t)
            seen.add(t)

    return {
        "response": last_msg.content,
        "structured_data": structured_data if structured_data else None,
        "tools_used": tools_used_deduped if tools_used_deduped else None,
        "preview_markdown": preview_markdown,
        "citations": citations if citations else None,
    }

def _is_toolless_greeting(text: str) -> bool:
    """
    Allow short greeting/ack messages to pass without tool calls.
    """
    if not text:
        return False
    lower = text.lower()
    greet_terms = ["hello", "hi", "hey", "welcome", "glad to help", "how can i help", "thanks for reaching"]
    guard_terms = ["property", "project", "apartment", "villa", "price", "budget", "bedroom", "dubai", "city", "book", "booking", "visit", "lead", "listing"]
    if any(term in lower for term in guard_terms):
        return False
    if len(lower) <= 140 and any(term in lower for term in greet_terms):
        return True
    return False

def _is_toolless_greeting_any(response_text: str, user_text: str) -> bool:
    """
    Skip guard if either the assistant reply or the user message is a simple greeting.
    """
    return _is_toolless_greeting(response_text) or _is_toolless_greeting(user_text)

def _is_clarifying_question(text: str) -> bool:
    """
    Allow short clarifying questions (e.g., asking which property) to pass without tools.
    """
    if not text:
        return False
    lower = text.lower()
    if len(lower) > 240:
        return False
    keywords = ["which property", "which project", "specify", "clarify", "tell me the name", "which listing"]
    if any(k in lower for k in keywords):
        return True
    if "?" in lower and ("property" in lower or "project" in lower or "listing" in lower):
        return True
    return False


@api.post("/agents/chat", response=ChatResponse)
async def chat(request, payload: ChatRequest):
    conversation_id = payload.conversation_id or str(uuid.uuid4())
    user_text = payload.message or ""
    config = {
        "configurable": {"thread_id": conversation_id},
        "recursion_limit": 8,
    }
    initial_state = {"messages": [HumanMessage(content=payload.message)]}
    try:
        result = await agent_app.ainvoke(initial_state, config=config)
    except GraphRecursionError:
        return {
            "response": "I'm looping on this request. Please adjust filters (city, budget, bedrooms) and try again.",
            "conversation_id": conversation_id,
            "data": None,
            "tools_used": None,
            "preview_markdown": None,
            "citations": None,
        }
    payload_out = _extract_structured(result)

    # Hard guard: if no tool outputs (no preview, no citations, no shortlist), avoid invented projects
    if (
        not payload_out["tools_used"]
        and not payload_out["preview_markdown"]
        and not payload_out["citations"]
        and not _is_toolless_greeting_any(payload_out["response"], user_text)
        and not _is_clarifying_question(payload_out["response"])
    ):
        return {
            "response": "I couldn't run SQL/RAG yet because key filters are missing. Please share city, budget range, and bedrooms so I can search.",
            "conversation_id": conversation_id,
            "data": None,
            "tools_used": None,
            "preview_markdown": None,
            "citations": None,
        }

    return {
        "response": payload_out["response"],
        "conversation_id": conversation_id,
        "data": payload_out["structured_data"],
        "tools_used": payload_out["tools_used"],
        "preview_markdown": payload_out["preview_markdown"],
        "citations": payload_out["citations"],
    }


@api.get("/agents/chat/stream")
def chat_stream(request, message: str, conversation_id: Optional[str] = None):
    """
    Stream assistant response as SSE (simulated at server). Final event carries metadata.
    """
    conv_id = conversation_id or str(uuid.uuid4())
    config = {
        "configurable": {"thread_id": conv_id},
        "recursion_limit": 8,
    }

    async def run_agent():
        initial_state = {"messages": [HumanMessage(content=message)]}
        return await agent_app.ainvoke(initial_state, config=config)

    def event_stream():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            try:
                result = loop.run_until_complete(run_agent())
            except GraphRecursionError:
                guard = {
                    "done": True,
                    "conversation_id": conv_id,
                    "response": "I'm looping on this request. Please adjust filters (city, budget, bedrooms) and try again.",
                    "tools_used": None,
                    "data": None,
                    "preview_markdown": None,
                    "citations": None,
                }
                yield f"data: {json.dumps(guard)}\n\n"
                return
            payload = _extract_structured(result)
            text = payload["response"] or ""
            for i in range(0, len(text), 20):
                chunk = text[: i + 20]
                yield f"data: {json.dumps({'chunk': chunk})}\n\n"
            if (
                not payload["tools_used"]
                and not payload["preview_markdown"]
                and not payload["citations"]
                and not _is_toolless_greeting_any(payload["response"], message or "")
                and not _is_clarifying_question(payload["response"])
            ):
                # Hard guard streaming path
                final_guard = {
                    "done": True,
                    "conversation_id": conv_id,
                    "response": "I couldn't run SQL/RAG yet because key filters are missing. Please share city, budget range, and bedrooms so I can search.",
                    "tools_used": None,
                    "data": None,
                    "preview_markdown": None,
                    "citations": None,
                }
                yield f"data: {json.dumps(final_guard)}\n\n"
                return
            final_payload = {
                "done": True,
                "conversation_id": conv_id,
                "response": payload["response"],
                "tools_used": payload["tools_used"],
                "data": payload["structured_data"],
                "preview_markdown": payload["preview_markdown"],
                "citations": payload["citations"],
            }
            yield f"data: {json.dumps(final_payload)}\n\n"
        finally:
            loop.close()

    return StreamingHttpResponse(event_stream(), content_type="text/event-stream")
