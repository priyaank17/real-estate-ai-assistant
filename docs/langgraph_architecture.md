# LangGraph Architecture (Silver Land Concierge)

```mermaid
flowchart TD
  UI[Frontend / index.html] -->|POST /api/agents/chat + conversation_id| API
  subgraph Django_Ninja
    API[agents/api.py (Ninja endpoint)] -->|thread_id config| Graph
    API -->|hard guard (no tools)| Guard
  end
  subgraph LangGraph_Agent
    Graph[agents/graph.py StateGraph + MemorySaver]
    Intent[extract_intent_filters (tools/intent_tool.py)]
    SQL[execute_sql_query (tools/sql_tool.py)]
    RAG[search_rag (tools/rag_tool.py)]
    UICTX[update_ui_context (tools/ui_tool.py)]
    BOOK[book_viewing (tools/booking_tool.py)]
    INV[analyze_investment]
    COMP[compare_projects]
    WEB[web_search]
  end
  Graph --> Intent
  Graph --> SQL
  Graph --> RAG
  Graph --> UICTX
  Graph --> BOOK
  Graph --> INV
  Graph --> COMP
  Graph --> WEB
  SQL --> UICTX
  RAG --> UICTX
  UICTX --> API
  Graph -->|response| API
  Guard -->|fallback msg| UI
  API -->|JSON: response, preview_markdown, citations, tools_used, shortlist| UI
```

## Flow (per turn)
1. **Frontend** sends `message` + `conversation_id` (persisted in localStorage).
2. **API** calls the LangGraph app with `thread_id=conversation_id` (MemorySaver keeps conversation state).
3. **Agent (graph)** runs with the system prompt. It calls `extract_intent_filters` first to pull project/developer/city/price/bedrooms/property_type/features.
4. Based on intent, the agent triggers:
   - `execute_sql_query` for structured search (primary).
   - `search_rag` for fuzzy/amenity/description or when SQL is empty (and often both).
   - Other tools as needed: `analyze_investment`, `compare_projects`, `book_viewing`, `web_search` (last resort), and `update_ui_context` to push shortlist IDs to the UI.
5. Tool messages (with rows/ids/preview/citations) are returned to the agent, which synthesizes the user-facing reply.
6. **API** extracts `tools_used`, `preview_markdown`, `citations`, and shortlist data for the UI. Hard guard: if no tool fired and it wasn’t a greeting/clarifier, return a safe “missing filters” message.
7. **Frontend** renders the assistant reply, per-message tools_used, shortlist, optional preview table, and citations toggle.

## How tools interact
- **Intent**: parses filters; no data access.
- **SQL**: generates/runs SQL via Vanna; returns rows, `project_ids`, and a preview table (only when shortlist exists).
- **RAG**: semantic search over descriptions/features; returns `results` and `project_ids` (no preview table by design).
- **UI context**: called when `project_ids` exist to sync shortlist with the frontend.
- **Booking**: writes leads/visit_bookings when the user confirms a visit.
- **Investment/Comparison/Web**: specialized branches; web is last resort when local data can’t answer.

## Prompt vs Graph Logic (trade-offs)
- **System prompt (current approach)**:
  - Pros: Fast to adjust behavior; co-locates policy and reasoning in one place; fewer code changes.
  - Cons: Less deterministic; the model might ignore instructions; harder to enforce strict ordering of tool calls.
- **Graph/state logic (conditional edges, nodes)**:
  - Pros: Deterministic routing (e.g., always call intent → SQL → fallback RAG); clearer separation of control flow; easier to test.
  - Cons: More code/config changes; added complexity; risk of rigidity if over-constrained.

Practical guidance:
- Keep high-level goals and style in the prompt (what to achieve, how to speak).
- Encode **must-run** behaviors in the graph/tooling layer (e.g., always run intent extraction; if SQL returns 0, run RAG; if project/developer present, run RAG+SQL before asking filters). That ensures compliance even if the model drifts.
- Use small helper tools (like the intent extractor) to feed structured signals into routing.
- If you see the model skipping tools despite the prompt, move that rule into the graph as an explicit node/edge decision.

## Why a greeting was blocked
- The API has a hard guard that only trips when **no tools fired** and the reply isn’t a greeting/clarifier. With a project name present, the prompt now tells the agent to call intent → SQL + RAG immediately; that should populate `tools_used` and bypass the guard. If you still hit the guard, it means the model didn’t call tools—then tighten routing in the graph (e.g., explicit “project name → RAG+SQL” edge).
