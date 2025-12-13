import os
import re
import io
import contextlib
import json
import math
from typing import TypedDict, Annotated, List, Dict, Any, Optional
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from langchain_core.messages import BaseMessage, SystemMessage, HumanMessage, ToolMessage, AIMessage
from langchain_openai import AzureChatOpenAI, ChatOpenAI
import operator
import logging

from helpers.vanna import get_vanna_client
from tools.sql_tool import MAX_ROWS_RETURNED
from tools.investment_tool import analyze_investment
from tools.comparison_tool import compare_properties
from agents.models import Lead

logger = logging.getLogger(__name__)
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

# Define State
class AgentState(TypedDict, total=False):
    messages: Annotated[List[BaseMessage], operator.add]
    intent: Dict[str, Any]
    intent_flags: Dict[str, bool]
    sql: Dict[str, Any]
    rag: Dict[str, Any]
    web: Dict[str, Any]
    shortlist: List[str]
    preview_markdown: Optional[str]
    selected_project_id: Optional[str]
    selected_project_name: Optional[str]
    lead_name: Optional[str]
    lead_email: Optional[str]
    lead_id: Optional[str]
    lead_city: Optional[str]
    preferred_date: Optional[str]
    detail: Dict[str, Any]
    investment: Dict[str, Any]
    comparison: Dict[str, Any]

# System prompt kept minimal; routing handled via explicit graph nodes.
SYSTEM_PROMPT = """You are a property concierge.
- Use only tool outputs; do not invent projects or cities.
- Recommend up to 3 matches with name, city, starting price/band, and key features.
- If tools return nothing, say so plainly and ask for missing filters (city/bed/budget) or offer close alternatives.
- Assume prices are USD; if another currency is given, clarify or convert approximately before filtering.
- Only mention projects explicitly returned by the current tool results/shortlist; never invent or reuse prior names. If there are no project names, say no matches.
- When detail/amenity info is provided (features/facilities/description), summarize it directly instead of saying “not listed.”
- Invite a property visit: when the user shows interest or you list matches, politely offer to book a viewing and request name + email (use any already provided).
- Do not mention tool names in your reply."""

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
    Deterministic LangGraph:
    1) extract_intent_filters
    2) execute_sql_query using current filters
    3) fetch_project_row for selected project (amenities/description)
    4) update_ui_context when shortlist exists
    5) booking when booking intent + shortlist
    6) synthesize response with LLM (minimal prompt)
    """
    model = _get_chat_model()
    tools_map = {}
    for t in tools:
        name = getattr(t, "name", None) or getattr(t, "__name__", "")
        fn = getattr(t, "func", None) or t
        tools_map[name] = fn

    # Helper: get last human text
    def _last_user_text(state: AgentState) -> str:
        for msg in reversed(state["messages"]):
            if isinstance(msg, HumanMessage):
                return msg.content
        return ""

    # Helper: build natural query text for SQL
    def _build_sql_text(intent: dict, user_text: str, state: AgentState) -> str:
        parts = []
        if intent.get("project_name"):
            parts.append(f"project named {intent['project_name']}")
        if intent.get("developer"):
            parts.append(f"by developer {intent['developer']}")
        city = state.get("lead_city") or intent.get("city") or state.get("intent", {}).get("city")
        if city:
            parts.append(f"in {city}")
        beds = intent.get("bedrooms") if intent.get("bedrooms") is not None else state.get("intent", {}).get("bedrooms")
        if beds is not None:
            parts.append(f"{beds} bedrooms")
        if intent.get("property_type") or state.get("intent", {}).get("property_type"):
            parts.append(intent.get("property_type") or state.get("intent", {}).get("property_type"))
        if intent.get("price_min") is not None or state.get("intent", {}).get("price_min") is not None:
            parts.append(f"price >= {intent.get('price_min') or state.get('intent', {}).get('price_min')}")
        if intent.get("price_max") is not None or state.get("intent", {}).get("price_max") is not None:
            parts.append(f"price <= {intent.get('price_max') or state.get('intent', {}).get('price_max')}")
        if intent.get("must_have_features"):
            parts.append("features: " + ", ".join(intent["must_have_features"]))
        base = "Find properties " + (" ".join(parts) if parts else user_text)
        return base.strip()

    def _like_term(term: str) -> str:
        # Normalize term for LIKE: lower, replace punctuation/spaces with %
        import re
        t = term.lower()
        t = re.sub(r"[^a-z0-9]+", "%", t)
        t = re.sub(r"%{2,}", "%", t).strip("%")
        return t

    def _parse_booking_intent(user_text: str) -> Dict[str, Any]:
        lower = user_text.lower()
        booking_keywords = ["book", "schedule", "visit", "tour", "viewing", "appointment"]
        has_booking_kw = any(k in lower for k in booking_keywords)
        email = None
        m = re.search(r"([\w.+-]+@[\w-]+\.[\w.-]+)", user_text)
        if m:
            email = m.group(1)
        name = None
        mname = re.search(r"(?:name\\s*[:=]\\s*|i am\\s+|i'm\\s+)([A-Za-z][A-Za-z\\s]{1,60})", user_text, re.IGNORECASE)
        if mname:
            name = mname.group(1).strip().strip(",.")
        return {"has_booking_kw": has_booking_kw, "email": email, "name": name}

    def _has_booking_intent(state: AgentState, user_text: str) -> bool:
        b = _parse_booking_intent(user_text)
        if b.get("has_booking_kw"):
            return True
        if state.get("lead_email") or b.get("email"):
            return True
        return False

    def _is_detail_query(user_text: str) -> bool:
        lower = user_text.lower()
        keywords = [
            "amenity",
            "amenities",
            "amenties",  # common misspelling
            "facility",
            "facilities",
            "facilty",  # common misspelling
            "offering",
            "offerings",
            "feature",
            "features",
            "description",
            "what is there",
            "what does it have",
        ]
        return any(k in lower for k in keywords)

    def _is_similar_query(user_text: str) -> bool:
        lower = user_text.lower()
        keywords = ["similar", "like this", "like that", "alternatives", "other options", "similar projects"]
        return any(k in lower for k in keywords)

    def _pick_project(state: AgentState) -> Dict[str, Optional[str]]:
        shortlist = state.get("shortlist") or []
        if not shortlist:
            return {"project_id": None, "project_name": None}
        # If already selected, keep
        if state.get("selected_project_id"):
            return {"project_id": state.get("selected_project_id"), "project_name": state.get("selected_project_name")}
        # Default to first shortlist item
        return {"project_id": shortlist[0], "project_name": None}

    def intent_node(state: AgentState):
        user_text = _last_user_text(state)
        intent = tools_map["extract_intent_filters"](user_text)
        booking = _parse_booking_intent(user_text)
        intent_flags = {
            "is_greeting": intent.get("is_greeting", False),
            "is_off_topic": intent.get("is_off_topic", False),
            "is_investment": intent.get("is_investment", False),
            "is_comparison": intent.get("is_comparison", False),
            "is_detail_question": intent.get("is_detail_question", False),
        }
        updates: Dict[str, Any] = {"messages": [], "intent": intent, "intent_flags": intent_flags}
        # If this is NOT a project/developer/detail query, clear stale detail/selection
        if not intent.get("project_name") and not intent.get("developer") and not _is_detail_query(user_text):
            updates["detail"] = {}
            updates["selected_project_id"] = None
            updates["selected_project_name"] = None
        # Short-circuit: if booking intent detected early, jump to booking
        if _has_booking_intent(state, user_text):
            updates["messages"] = [
                ToolMessage(
                    name="extract_intent_filters",
                    content=intent,
                    tool_call_id="intent",
                )
            ]
            updates["intent"] = intent
            return updates
        if intent.get("lead_name"):
            updates["lead_name"] = intent.get("lead_name")
        if intent.get("lead_email"):
            updates["lead_email"] = intent.get("lead_email")
            # Upsert lead record immediately (so leads are captured even before booking)
            try:
                first = intent.get("lead_name") or ""
                last = ""
                if first and " " in first:
                    parts = first.split()
                    first, last = parts[0], " ".join(parts[1:])
                lead_obj, _ = Lead.objects.get_or_create(
                    email=intent["lead_email"],
                    defaults={"first_name": first or "Guest", "last_name": last, "preferences": user_text},
                )
                updates["lead_id"] = str(lead_obj.id)
                # Update name/preferences if missing
                needs_save = False
                if first and not lead_obj.first_name:
                    lead_obj.first_name = first
                    needs_save = True
                if last and not lead_obj.last_name:
                    lead_obj.last_name = last
                    needs_save = True
                if user_text and (not lead_obj.preferences):
                    lead_obj.preferences = user_text
                    needs_save = True
                if needs_save:
                    lead_obj.save()
            except Exception as e:
                logger.info(f"[intent_node] lead upsert failed: {e}")
        # Fallback: if user is asking for amenities/details but intent extractor missed project_name,
        # keep the raw text as a tentative selector for downstream detail lookup.
        if not intent.get("project_name") and _is_detail_query(user_text):
            updates["selected_project_name"] = user_text.strip()
        if booking.get("name"):
            updates["lead_name"] = booking["name"]
        if booking.get("email"):
            updates["lead_email"] = booking["email"]
        # Keep city/property filters sticky
        if intent.get("city"):
            updates["lead_city"] = intent["city"]
        logger.info(f"[intent_node] user_text='{user_text}' intent={intent}")
        tm = ToolMessage(
            name="extract_intent_filters",
            content=intent,
            tool_call_id="intent",
        )
        updates["messages"] = [tm]
        return updates

    def sql_node(state: AgentState):
        intent = state.get("intent", {}) or {}
        user_text = _last_user_text(state)
        query_text = _build_sql_text(intent, user_text, state)
        # If project/developer/features are present, prefer a manual LIKE search to catch partials across text fields.
        if intent.get("project_name") or intent.get("developer") or intent.get("must_have_features"):
            terms = []
            if intent.get("project_name"):
                terms.append(intent["project_name"])
            if intent.get("developer"):
                terms.append(intent["developer"])
            # Only add feature terms if no specific project name was given (avoid broadening detail queries)
            if not intent.get("project_name"):
                for feat in intent.get("must_have_features") or []:
                    terms.append(feat)
            # If no explicit term, fall back to the user text keyword
            if not terms and user_text:
                terms.append(user_text)

            keyword_clauses = []
            for term in terms:
                t = term.replace("'", "''")
                like_t = _like_term(term)
                keyword_clauses.append(
                    f"(LOWER(name) LIKE '%{like_t}%' OR LOWER(description) LIKE '%{like_t}%' "
                    f"OR LOWER(features) LIKE '%{like_t}%' OR LOWER(facilities) LIKE '%{like_t}%' "
                    f"OR LOWER(developer) LIKE '%{like_t}%' OR LOWER(city) LIKE '%{like_t}%')"
                )
            where_parts = []
            if keyword_clauses:
                where_parts.append("(" + " OR ".join(keyword_clauses) + ")")
            if intent.get("city"):
                c = intent["city"].replace("'", "''")
                where_parts.append(f"LOWER(city) LIKE '%{_like_term(intent['city'])}%'")
            where_sql = " AND ".join(where_parts) if where_parts else "1=1"
            like_query = f"SELECT * FROM agents_project WHERE {where_sql} LIMIT {MAX_ROWS_RETURNED}"
            try:
                vn = get_vanna_client()
                with contextlib.redirect_stdout(io.StringIO()):
                    df = vn.run_sql(like_query)
                if df is not None:
                    df = df.where(df.notnull(), None)
                    columns = list(df.columns)
                    limited_df = df.head(MAX_ROWS_RETURNED) if not df.empty else df
                    clean_df = limited_df.copy()
                    if "id" in clean_df.columns:
                        clean_df["id"] = clean_df["id"].apply(lambda value: str(value) if value is not None else None)
                    rows = [] if clean_df is None or clean_df.empty else clean_df.to_dict(orient="records")
                    project_ids = [row["id"] for row in rows if row.get("id")]
                    payload = {
                        "sql": like_query,
                        "columns": columns,
                        "rows": rows,
                        "row_count": len(df) if df is not None else 0,
                        "truncated": len(df) > len(rows) if df is not None else False,
                        "preview_markdown": "",
                        "project_ids": project_ids,
                        "source_tool": "execute_sql_query",
                    }
                else:
                    payload = {
                        "sql": like_query,
                        "columns": [],
                        "rows": [],
                        "row_count": 0,
                        "truncated": False,
                        "project_ids": [],
                        "preview_markdown": "",
                        "source_tool": "execute_sql_query",
                    }
            except Exception as e:
                logger.info(f"[sql_node] fallback LIKE failed: {e}")
                payload = tools_map["execute_sql_query"](query_text)
        else:
            payload = tools_map["execute_sql_query"](query_text)
        row_names = []
        for r in payload.get("rows", [])[:15]:
            nm = r.get("name") or r.get("project_name")
            row_names.append(nm or "<?>")
        logger.info(f"[sql_node] query_text='{query_text}' rows={len(payload.get('rows', []))} error={payload.get('error')} names_sample={row_names}")
        tm = ToolMessage(
            name="execute_sql_query",
            content=payload,
            tool_call_id="sql",
        )
        updates = {"messages": [tm], "sql": payload}
        shortlist = list(dict.fromkeys(payload.get("project_ids") or []))
        updates["shortlist"] = shortlist  # replace prior shortlist every SQL turn
        updates["preview_markdown"] = payload.get("preview_markdown") or None
        # If user mentioned a project, set selection (fallback to first row id if exists)
        if intent.get("project_name"):
            updates["selected_project_name"] = intent["project_name"]
            first_id = None
            if shortlist:
                first_id = shortlist[0]
            elif payload.get("rows"):
                first_id = payload["rows"][0].get("id") or payload["rows"][0].get("project_id")
            if first_id:
                updates["selected_project_id"] = first_id
        return updates

    def booking_node(state: AgentState):
        user_text = _last_user_text(state)
        booking = _parse_booking_intent(user_text)
        lead_name = state.get("lead_name") or booking.get("name")
        lead_email = state.get("lead_email") or booking.get("email")
        intent = state.get("intent") or {}
        pick = _pick_project(state)
        project_id = pick.get("project_id")
        project_name = pick.get("project_name") or intent.get("project_name")
        # If no project_id but we have a name, try to resolve directly
        if not project_id and project_name:
            payload = tools_map["fetch_project_row"](project_name)
            if payload.get("project_id"):
                project_id = payload.get("project_id")
                state["selected_project_id"] = project_id
                state["selected_project_name"] = payload.get("project_name")
        city = state.get("lead_city") or state.get("intent", {}).get("city") or ""
        pref_date = state.get("preferred_date") or ""
        if not project_id:
            payload = {
                "message": "I can book your visit. Please confirm the project and share your email (and name) to proceed.",
                "source_tool": "book_viewing",
            }
        elif not lead_email:
            payload = {
                "message": "I can book your visit. Please share an email (and name, if not provided) to confirm the booking.",
                "source_tool": "book_viewing",
            }
        else:
            payload = tools_map["book_viewing"](
                project_id=project_id,
                customer_name=lead_name or "",
                customer_email=lead_email,
                city=city,
                preferred_date=pref_date,
                preferences=user_text,
            )
        tm = ToolMessage(
            name="book_viewing",
            content=payload,
            tool_call_id="booking",
        )
        # Send a human-friendly confirmation without invoking the LLM
        msg_text = payload.get("message") if isinstance(payload, dict) else ""
        extra_bits = []
        if isinstance(payload, dict):
            if payload.get("project_name"):
                extra_bits.append(f"Project: {payload['project_name']}")
            if payload.get("customer_name"):
                extra_bits.append(f"Name: {payload['customer_name']}")
            if payload.get("customer_email"):
                extra_bits.append(f"Email: {payload['customer_email']}")
            if payload.get("booking_id"):
                extra_bits.append(f"Booking ID: {payload['booking_id']}")
        if msg_text and extra_bits:
            msg_text = msg_text + "\n" + " | ".join(extra_bits)
        ai_msg = AIMessage(content=msg_text or "Visit noted. Please confirm project and email to finalize the booking.")

        updates: Dict[str, Any] = {"messages": [tm, ai_msg], "booking": payload}
        if project_id:
            updates["selected_project_id"] = project_id
        if pick.get("project_name"):
            updates["selected_project_name"] = pick["project_name"]
        return updates

    def detail_node(state: AgentState):
        # Prefer an explicit selection; otherwise, pick best match from SQL rows/shortlist
        proj = state.get("selected_project_id") or state.get("selected_project_name")
        shortlist = state.get("shortlist") or []
        sql_rows = state.get("sql", {}).get("rows", [])
        intent_proj = (state.get("intent") or {}).get("project_name")

        def _norm_txt(txt: str) -> str:
            import re
            return re.sub(r"[^a-z0-9]+", "", txt.lower())

        # If intent has a project name, try to pick the matching SQL row first
        best_row = None
        if intent_proj and sql_rows:
            intent_norm = _norm_txt(intent_proj)
            for r in sql_rows:
                raw_name = (r.get("name") or r.get("project_name") or "")
                name_norm = _norm_txt(raw_name)
                if not raw_name or raw_name.lower().startswith("project name not available"):
                    continue
                if intent_norm and intent_norm in name_norm:
                    best_row = r
                    break
        # Build shortlist if absent
        if not shortlist and sql_rows:
            shortlist = [r.get("id") or r.get("project_id") for r in sql_rows if r.get("id") or r.get("project_id")]
            shortlist = [s for s in shortlist if s]
        # If we found a matching row, prefer its id/name
        if best_row:
            bid = best_row.get("id") or best_row.get("project_id")
            if bid:
                proj = bid
                state["selected_project_id"] = bid
                if best_row.get("name"):
                    state["selected_project_name"] = best_row.get("name")
        # If no match yet and we have an intent project name, try direct fetch by name (even if not in SQL rows)
        if not best_row and intent_proj:
            direct_payload = tools_map["fetch_project_row"](intent_proj)
            if direct_payload.get("project_id"):
                tm = ToolMessage(
                    name="fetch_project_row",
                    content=direct_payload,
                    tool_call_id="detail",
                )
                logger.info(f"[detail_node] direct fetch by name '{intent_proj}' payload_keys={list(direct_payload.keys())}")
                return {
                    "messages": [tm],
                    "detail": direct_payload,
                    "selected_project_id": direct_payload.get("project_id"),
                    "selected_project_name": direct_payload.get("project_name"),
                }
            else:
                logger.info(f"[detail_node] direct fetch by name '{intent_proj}' failed")
        # If still no match, do not force detail; let listing handle
        if not proj:
            return {}
        # If still no explicit selection, fallback to shortlist first item
        if not proj and shortlist:
            proj = shortlist[0]
            # backfill name if available
            for r in sql_rows:
                rid = r.get("id") or r.get("project_id")
                if rid and str(rid) == str(proj) and r.get("name"):
                    state["selected_project_name"] = r.get("name")
                    break
        if not proj:
            # Fallback to user text as project name
            proj = _last_user_text(state)
        if not proj:
            return {}
        payload = tools_map["fetch_project_row"](proj)
        logger.info(f"[detail_node] project_selector='{proj}' payload_keys={list(payload.keys())}")
        tm = ToolMessage(
            name="fetch_project_row",
            content=payload,
            tool_call_id="detail",
        )
        updates: Dict[str, Any] = {
            "messages": [tm],
            "detail": payload,
            "selected_project_id": payload.get("project_id"),
            "selected_project_name": payload.get("project_name"),
        }
        return updates

    def ui_node(state: AgentState):
        shortlist = state.get("shortlist") or []
        if shortlist:
            logger.info(f"[ui_node] shortlist_count={len(shortlist)} ids={shortlist[:5]}")
            ui_payload = {"shortlisted_project_ids": shortlist}
            try:
                tools_map["update_ui_context"](shortlisted_project_ids=shortlist)
            except TypeError:
                tools_map["update_ui_context"]({"shortlisted_project_ids": shortlist})
            tm = ToolMessage(
                name="update_ui_context",
                content=ui_payload,
                tool_call_id="ui",
            )
            return {"messages": [tm]}
        return {}

    def investment_node(state: AgentState):
        intent = state.get("intent") or {}
        shortlist = state.get("shortlist") or []
        project_id = state.get("selected_project_id")
        if not project_id and shortlist:
            project_id = shortlist[0]
        try:
            payload = analyze_investment.invoke({"project_id": project_id or "", "city": intent.get("city") or "", "budget": intent.get("price_max")})
        except Exception as e:
            payload = {"error": f"analyze_investment failed: {e}", "source_tool": "analyze_investment"}
        tm = ToolMessage(
            name="analyze_investment",
            content=payload,
            tool_call_id="investment",
        )
        updates = {"messages": [tm], "investment": payload}
        return updates

    def comparison_node(state: AgentState):
        shortlist = state.get("shortlist") or []
        sql_rows = state.get("sql", {}).get("rows", []) or []
        # Use shortlist ids; if fewer than 2, fall back to ids from SQL rows
        ids = shortlist[:2]
        if len(ids) < 2 and sql_rows:
            extra_ids = []
            for r in sql_rows:
                pid = r.get("id") or r.get("project_id")
                if pid and pid not in ids and pid not in extra_ids:
                    extra_ids.append(pid)
                if len(ids) + len(extra_ids) >= 2:
                    break
            ids.extend(extra_ids)
        try:
            payload = compare_properties.invoke({"project_ids": ids})
        except Exception as e:
            payload = {"error": f"compare_properties failed: {e}", "source_tool": "compare_properties"}
        tm = ToolMessage(
            name="compare_properties",
            content=payload,
            tool_call_id="comparison",
        )
        updates = {"messages": [tm], "comparison": payload}
        return updates

    def respond_node(state: AgentState):
        user_text = _last_user_text(state)
        sql = state.get("sql") or {}
        rag = state.get("rag") or {}
        booking = state.get("booking") or {}
        shortlist = state.get("shortlist") or []
        preview_md = state.get("preview_markdown") or sql.get("preview_markdown") or ""
        detail = state.get("detail") or {}
        intent_flags = state.get("intent_flags") or {}
        # If booking intent and booking payload exists, stop here with confirmation
        if booking and booking.get("message"):
            msg_text = booking.get("message")
            extra_bits = []
            if booking.get("project_name"):
                extra_bits.append(f"Project: {booking.get('project_name')}")
            if booking.get("customer_name"):
                extra_bits.append(f"Name: {booking.get('customer_name')}")
            if booking.get("customer_email"):
                extra_bits.append(f"Email: {booking.get('customer_email')}")
            if booking.get("booking_id"):
                extra_bits.append(f"Booking ID: {booking.get('booking_id')}")
            if extra_bits:
                msg_text += "\n" + " | ".join(extra_bits)
            return {"messages": [AIMessage(content=msg_text)]}
        # Detail mode only if detail matches current intent/shortlist/sql
        detail_mode = False
        if detail.get("project_id"):
            proj_id = str(detail.get("project_id"))
            intent_name = (state.get("intent") or {}).get("project_name")
            sql_ids = set(sql.get("project_ids") or [])
            shortlist_ids = set(shortlist or [])
            name_match = False
            if intent_name and detail.get("project_name"):
                name_match = intent_name.lower() in detail.get("project_name", "").lower()
            id_match = proj_id in sql_ids or proj_id in shortlist_ids
            if name_match or id_match or intent_name:
                detail_mode = True
            else:
                # stale detail; drop it
                detail = {}
                state["detail"] = {}
                state["selected_project_id"] = None
                state["selected_project_name"] = None
        row_count = sql.get("row_count", 0) or len(sql.get("rows", []))

        # If we have a booking payload with confirmation, short-circuit and return it directly
        if booking and booking.get("message"):
            msg_text = booking.get("message")
            extra_bits = []
            if booking.get("project_name"):
                extra_bits.append(f"Project: {booking.get('project_name')}")
            if booking.get("customer_name"):
                extra_bits.append(f"Name: {booking.get('customer_name')}")
            if booking.get("customer_email"):
                extra_bits.append(f"Email: {booking.get('customer_email')}")
            if booking.get("booking_id"):
                extra_bits.append(f"Booking ID: {booking.get('booking_id')}")
            if extra_bits:
                msg_text += "\n" + " | ".join(extra_bits)
            return {"messages": [AIMessage(content=msg_text)]}

        sql_projects = []
        sql_rows_preview = []
        top_listings = []
        allowed_ids = set(state.get("shortlist") or [])
        allowed_names = set()
        if not detail_mode:
            for row in sql.get("rows", []):
                proj_id = row.get("id") or row.get("project_id")
                name = row.get("name") or row.get("project_name")
                city = row.get("city")
                price = row.get("price")
                beds = row.get("bedrooms")
                if proj_id and name:
                    sql_projects.append(f"{name}" + (f" ({city})" if city else ""))
                    if proj_id in allowed_ids:
                        allowed_names.add(name)
                if len(sql_rows_preview) < 5:
                    sql_rows_preview.append(
                        f"- {name or 'Unknown'} | city={city} | bedrooms={beds} | price={price}"
                    )
                if len(top_listings) < 5 and name:
                    top_listings.append(
                        f"{name}" + (f" in {city}" if city else "") + (f" | price={price}" if price is not None else "")
                    )

        rag_projects = []
        rag_snippets = []
        total_ids = set(sql.get("project_ids") or [])
        for item in rag.get("results", []):
            proj_id = item.get("project_id")
            name = item.get("project_name")
            city = item.get("city")
            if name and name != "nan":
                rag_projects.append(f"{name}" + (f" ({city})" if city else ""))
                if proj_id and proj_id in allowed_ids:
                    allowed_names.add(name)
            if proj_id:
                total_ids.add(proj_id)
            snippet = item.get("snippet") or item.get("description_chunk")
            if snippet:
                rag_snippets.append(snippet[:400])
        # If detail data exists with id/name/description, treat it as allowed and add snippet
        dname = detail.get("project_name")
        did = detail.get("project_id")
        if dname and did:
            allowed_ids.add(did)
            allowed_names.add(dname)
            total_ids.add(did)
        detail_snippets = []
        if detail.get("description"):
            detail_snippets.append(str(detail["description"])[:600])
        if detail.get("features"):
            detail_snippets.append(f"Features: {detail['features']}")
        if detail.get("facilities"):
            detail_snippets.append(f"Facilities: {detail['facilities']}")
        if detail_snippets:
            rag_snippets.extend(detail_snippets)

        tool_context_parts = []
        tool_context_parts.append(f"User intent: {user_text}")
        if detail_mode:
            summary_bits = [
                f"{detail.get('project_name') or 'Unknown project'}",
                f"city={detail.get('city')}" if detail.get("city") else None,
                f"bedrooms={detail.get('bedrooms')}" if detail.get("bedrooms") is not None else None,
                f"price={detail.get('price')}" if detail.get("price") is not None else None,
            ]
            summary_bits = [b for b in summary_bits if b]
            tool_context_parts.append("Detail project: " + " | ".join(summary_bits))
            if detail.get("description"):
                tool_context_parts.append("Detail description: " + str(detail.get("description"))[:1200])
            if detail.get("features"):
                tool_context_parts.append(f"Detail features: {detail.get('features')}")
            if detail.get("facilities"):
                tool_context_parts.append(f"Detail facilities: {detail.get('facilities')}")
            # Include all columns for column-specific questions
            tool_context_parts.append("Detail full row: " + str({k: v for k, v in detail.items() if k not in {'source_tool'}}))
        else:
            tool_context_parts.append(f"SQL rows: {len(sql.get('rows', []))}")
            if sql_projects:
                tool_context_parts.append("SQL projects: " + "; ".join(sql_projects[:5]))
            if sql.get("error"):
                tool_context_parts.append(f"SQL error: {sql.get('error')}")
            tool_context_parts.append(f"RAG results: {len(rag.get('results', []))}")
            if rag_projects:
                tool_context_parts.append("RAG projects: " + "; ".join(rag_projects[:5]))
            if rag.get("message"):
                tool_context_parts.append(f"RAG message: {rag.get('message')}")
            if shortlist:
                tool_context_parts.append(f"Shortlist count: {len(shortlist)} (showing up to 5) -> " + ", ".join(shortlist[:5]))
            if preview_md:
                tool_context_parts.append("Preview markdown provided.")
            if rag_snippets:
                tool_context_parts.append("RAG snippets:\n- " + "\n- ".join(rag_snippets[:2]))
            if sql_rows_preview:
                tool_context_parts.append("SQL rows (sample):\n" + "\n".join(sql_rows_preview))
            # Ensure allowed_names not empty when we have rows
            if not allowed_names and sql_projects:
                allowed_names.update(sql_projects)
            if allowed_names:
                tool_context_parts.append("Allowed projects (use only these, max 3): " + "; ".join(list(allowed_names)[:5]))
            else:
                tool_context_parts.append("Allowed projects: none (do not invent names; say no matches)")
            if top_listings:
                tool_context_parts.append("Top listings (up to 5): " + "; ".join(top_listings))
            if total_ids:
                tool_context_parts.append(f"Total unique project ids from tools: {len(total_ids)}")
            if booking:
                tool_context_parts.append(f"Booking payload: {booking}")
            if row_count > 5:
                tool_context_parts.append(f"Show all hint: {row_count} results available; only a few shown here.")

        tool_context = "\n".join(tool_context_parts)

        logger.info(f"[respond_node] sql_rows={len(sql.get('rows', []))} rag_results={len(rag.get('results', [])) if isinstance(rag, dict) else 0} shortlist={len(shortlist)}")

        system_prompt = SYSTEM_PROMPT
        if detail_mode:
            system_prompt = (
                "You are a property concierge.\n"
                "- The user asked for project-specific details (amenities/features/facilities/description).\n"
                "- Use ONLY the provided detail info to summarize amenities/features/facilities. Do not say 'not listed' if features/facilities/description text is provided.\n"
                "- Do not list other projects.\n"
                "- Keep the answer concise and focused on the requested details."
            )
        else:
            if row_count > 0:
                system_prompt += "\n- You have SQL results; summarize up to 3 matches using those rows. Do NOT say 'no matches' when rows exist."

        msgs = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_text),
            HumanMessage(content="Tool results:\n" + tool_context),
        ]
        logger.info("[respond_node] LLM context:\n" + "\n".join([f"- {m.content}" for m in msgs if hasattr(m, 'content')]))
        # Send data payload separately so frontend can render full lists
        data_payload = {}
        if detail_mode and detail:
            data_payload["detail"] = detail
        if not detail_mode and sql.get("rows"):
            data_payload["rows"] = sql.get("rows")
            data_payload["row_count"] = row_count
            data_payload["shortlisted_project_ids"] = shortlist
            # Build a preview table for UI (all rows returned)
            try:
                import pandas as _pd
                df = _pd.DataFrame(sql.get("rows"))
                preview_cols = [c for c in ["id", "name", "city", "property_type", "bedrooms", "price", "status"] if c in df.columns]
                if preview_cols:
                    data_payload["preview_markdown"] = df.head(3)[preview_cols].to_markdown(index=False)
            except Exception:
                pass

        data_msg = None
        if data_payload:
            def _clean(obj):
                if isinstance(obj, float):
                    if math.isnan(obj) or math.isinf(obj):
                        return None
                    return obj
                if isinstance(obj, dict):
                    return {k: _clean(v) for k, v in obj.items()}
                if isinstance(obj, list):
                    return [_clean(x) for x in obj]
                return obj

            safe_payload = _clean(data_payload)
            data_msg = ToolMessage(
                name="data_sync",
                content=json.dumps(safe_payload, default=str, allow_nan=False),
                tool_call_id="data_sync",
            )
            logger.info(f"[respond_node] data_sync payload keys={list(data_payload.keys())}")

        response = model.invoke(msgs)
        if data_msg:
            return {"messages": [data_msg, response]}
        return {"messages": [response]}

    def after_intent(state: AgentState):
        user_text = _last_user_text(state)
        intent_flags = state.get("intent_flags") or {}
        if intent_flags.get("is_greeting"):
            logger.info("[route] after_intent -> guard (greeting)")
            return "guard"
        if intent_flags.get("is_off_topic"):
            logger.info("[route] after_intent -> guard (off_topic)")
            return "guard"
        if _has_booking_intent(state, user_text):
            logger.info("[route] after_intent -> booking (booking intent)")
            return "booking"
        logger.info("[route] after_intent -> sql")
        return "sql"

    def after_sql(state: AgentState):
        sql = state.get("sql") or {}
        intent = state.get("intent", {}) or {}
        row_count = sql.get("row_count", 0) or len(sql.get("rows", []))
        project_or_dev = intent.get("project_name") or intent.get("developer")
        has_features = bool(intent.get("must_have_features"))
        low_rows = row_count < 3
        user_text = _last_user_text(state)
        shortlist = state.get("shortlist") or []
        has_error = bool(sql.get("error"))
        selected_detail_requested = (state.get("selected_project_name") or state.get("selected_project_id")) and _is_detail_query(user_text)
        intent_flags = state.get("intent_flags") or {}
        detail_query = intent_flags.get("is_detail_question") or _is_detail_query(user_text)
        if _has_booking_intent(state, user_text) and (state.get("shortlist") or []):
            logger.info("[route] after_sql -> booking (booking intent + shortlist)")
            return "booking"
        if intent_flags.get("is_investment"):
            logger.info("[route] after_sql -> investment")
            return "investment"
        if intent_flags.get("is_comparison"):
            logger.info("[route] after_sql -> comparison")
            return "comparison"
        # Detail routing rules:
        # - Specific project + detail query -> detail
        # - Developer-only listing -> stay listing (ui)
        # - Similar-to-X -> stay listing (ui)
        if intent.get("project_name") and detail_query:
            logger.info(f"[route] after_sql -> detail (project detail query)")
            return "detail"
        if intent.get("project_name") and _is_similar_query(user_text):
            logger.info("[route] after_sql -> ui (similar projects request)")
            return "ui"
        if intent.get("developer") and not _is_detail_query(user_text):
            logger.info("[route] after_sql -> ui (developer listing)")
            return "ui"
        if detail_query and (shortlist or state.get("selected_project_id")):
            logger.info("[route] after_sql -> detail (detail query using shortlist/selection)")
            return "detail"
        if project_or_dev:
            logger.info(f"[route] after_sql -> detail (project/developer query)")
            return "detail"
        if selected_detail_requested:
            logger.info("[route] after_sql -> detail (detail requested on selected project)")
            return "detail"
        if (has_error or row_count == 0 or low_rows) and _is_detail_query(user_text):
            # Try detail fetch using user text when SQL is sparse/error
            logger.info(f"[route] after_sql -> detail (detail query fallback; row_count={row_count} error={has_error})")
            state["selected_project_name"] = intent.get("project_name") or user_text
            return "detail"
        if _is_detail_query(user_text) and shortlist:
            logger.info(f"[route] after_sql -> detail (detail query + shortlist={len(shortlist)})")
            if not intent.get("project_name"):
                state["selected_project_name"] = user_text
            return "detail"
        logger.info(f"[route] after_sql -> ui (row_count={row_count})")
        return "ui"

    def after_detail(state: AgentState):
        shortlist = state.get("shortlist") or []
        user_text = _last_user_text(state)
        if _has_booking_intent(state, user_text) and shortlist:
            logger.info(f"[route] after_detail -> booking (shortlist={len(shortlist)})")
            return "booking"
        return "ui"

    workflow = StateGraph(AgentState)
    workflow.add_node("intent", intent_node)
    workflow.add_node("sql", sql_node)
    workflow.add_node("detail", detail_node)
    workflow.add_node("ui", ui_node)
    workflow.add_node("booking", booking_node)
    workflow.add_node("investment", investment_node)
    workflow.add_node("comparison", comparison_node)
    workflow.add_node("respond", respond_node)
    def guard_node(state: AgentState):
        flags = state.get("intent_flags") or {}
        if flags.get("is_off_topic"):
            content = "I'm focused on real estate for Silver Land. Please ask about properties, budgets, amenities, or booking a visit."
        else:
            content = "Hello! I’m Silver Land’s real estate assistant. Share a city, budget, and bedrooms to get recommendations."
        return {"messages": [AIMessage(content=content)]}

    workflow.add_node("guard", guard_node)

    workflow.set_entry_point("intent")
    workflow.add_conditional_edges("intent", after_intent, {"sql": "sql", "booking": "booking", "guard": "guard"})
    workflow.add_conditional_edges("sql", after_sql, {"detail": "detail", "ui": "ui", "booking": "booking", "investment": "investment", "comparison": "comparison"})
    workflow.add_conditional_edges("detail", after_detail, {"ui": "ui", "booking": "booking"})
    workflow.add_edge("guard", END)
    workflow.add_edge("ui", "respond")
    workflow.add_edge("investment", "respond")
    workflow.add_edge("comparison", "respond")
    # Booking returns confirmation directly; end the turn
    workflow.add_edge("booking", END)
    workflow.add_edge("respond", END)

    memory = MemorySaver()
    return workflow.compile(checkpointer=memory)

def create_agent_graph(tools: List, use_react: bool = False):
    """
    Factory function - creates agent with tools and memory.
    
    Args:
        tools: List of LangChain tools
        use_react: If True, use ReAct agent. If False, use custom graph (default, more stable).
    
    Returns:
        Compiled agent with memory
    """
    return create_custom_agent_graph(tools)

# For backwards compatibility and testing
if __name__ == "__main__":
    from tools.sql_tool import execute_sql_query
    from tools.intent_tool import extract_intent_filters
    from tools.ui_tool import update_ui_context
    from tools.booking_tool import book_viewing
    from tools.sql_tool import fetch_project_row
    
    local_tools = [extract_intent_filters, execute_sql_query, fetch_project_row, update_ui_context, book_viewing]
    
    # Test custom implementation
    print("Testing Custom Graph...")
    custom_app = create_agent_graph(local_tools, use_react=False)
    
    print("✅ Custom graph available")
else:
    app = None
