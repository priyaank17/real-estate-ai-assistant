# Silver Land Properties AI Assistant — LangGraph agentic flow

Agentic real-estate concierge built on Django + LangGraph where the LLM dynamically chooses tools (SQL, RAG, web search, booking, investment, comparison). If you prefer a deterministic workflow, use the `feature/langgraph-tools` branch.

---

## Quick Start (main branch)

**Clone & install**
```bash
git clone https://github.com/priyaank17/real-estate-ai-assistant.git
cd real-estate-ai-assistant
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

**Configure env & migrate**
```bash
cp .env.example .env   # then edit with your keys
python manage.py migrate
```

**Seed data + ingest RAG**
```bash
python scripts/seed_database.py
python scripts/ingest_rag.py        # required for semantic search over descriptions/facilities
```

**Train Vanna (text-to-SQL)**
```bash
python scripts/vanna_setup.py   # primes Vanna with schema + sample queries
```

**Run backend**
```bash
python manage.py runserver 8000
```

**Optional: static frontend**
```bash
python -m http.server 4000 -d frontend   # visit http://localhost:4000
```

Minimal `.env` (Azure recommended):
```bash
AZURE_OPENAI_API_KEY="..."
AZURE_OPENAI_ENDPOINT="https://<resource>.openai.azure.com/"
AZURE_OPENAI_API_VERSION="2024-05-01-preview"
AZURE_OPENAI_CHAT_DEPLOYMENT="gpt-4o-mini"
AZURE_OPENAI_EMBED_DEPLOYMENT="text-embedding-3-small"  # needed for RAG
# Fallback: OPENAI_API_KEY=... OPENAI_LLM_MODEL=gpt-4o-mini
```

---

## Key tables
- `projects` (`agents_project`): property metadata (name, city, beds, price, description, features/facilities, etc.).
- `leads` (`agents_lead`): first name, last name, email, preferences.
- `bookings` (`agents_booking`): legacy bookings.
- `visit_bookings` (`visit_bookings`): confirmed visit bookings (used by `book_viewing`).

---

## Project structure (main)
```
real-estate-ai-assistant/
├── agents/          # Django app (API, LangGraph wiring, models)
├── tools/           # SQL, intent, web, RAG, booking, investment, comparison, UI sync
├── frontend/        # Static chat UI
├── scripts/         # seed_database.py, vanna_setup.py, ingest_rag.py
├── helpers/         # Vanna client, vectorstore helpers
├── docs/            # Architecture/setup docs
├── data/            # properties.csv and other seeds
├── silver_land/     # Django project settings/urls/wsgi
├── db.sqlite3       # default SQLite DB
├── tests/           # pytest-based tests (tools + API)
└── manage.py        # Django entrypoint
```

---

## Architecture (main, agentic LangGraph)

```mermaid
flowchart TD
  UI[frontend/index.html\\nstatic chat] -->|/api/agents/chat| API
  API[agents/api.py\\nNinja endpoint] --> Agent

  subgraph LangGraph_agentic
    direction TB
    Agent(Human/LLM core\\nchooses tools) --> SQL[execute_sql_query\\n(Vanna)]
    Agent --> RAG[search_rag\\n(Chroma/embeddings)]
    Agent --> WEB[web_search]
    Agent --> BOOK[book_viewing]
    Agent --> INVEST[analyze_investment]
    Agent --> COMPARE[compare_projects]
    Agent --> UICTX[update_ui_context]
    SQL --> Agent
    RAG --> Agent
    WEB --> Agent
    BOOK --> Agent
    INVEST --> Agent
    COMPARE --> Agent
    UICTX --> Agent
  end
```

---

## Tools (main flow)
- `extract_intent_filters` — parses filters, project/developer hints, and flags.
- `execute_sql_query` — Vanna text-to-SQL over the relational DB.
- `search_rag` — semantic search over descriptions/facilities (requires embeddings + ingestion).
- `web_search` — external search for out-of-DB questions.
- `book_viewing` — creates visit bookings and captures leads.
- `analyze_investment` — simple ROI/score heuristics.
- `compare_projects` — side-by-side comparison of projects.
- `update_ui_context` — syncs shortlist/UI hints.

---

## Models used
- **Chat/agent + intent LLM**: Azure OpenAI (`AZURE_OPENAI_*`) if set; otherwise OpenAI (`OPENAI_API_KEY`, `OPENAI_LLM_MODEL`). Optional Ollama for intent if you set `USE_OLLAMA_FOR_INTENT=true` and `OLLAMA_MODEL` (fallback to Azure/OpenAI if not).
- **Text-to-SQL (Vanna)**: uses the same Azure/OpenAI keys; run `scripts/vanna_setup.py` to seed examples.
- **Embeddings**: required for semantic search; `scripts/ingest_rag.py` uses `AZURE_OPENAI_EMBED_DEPLOYMENT` or `OPENAI_EMBEDDING_MODEL`.

---

## API

### `POST /api/agents/chat`
Single-turn chat (optionally pass `conversation_id`).
```bash
curl -X POST http://localhost:8000/api/agents/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Find apartments in Dubai under 2M"}'
```
Response contains: `response`, `conversation_id`, optional `data` (rows/detail), `tools_used`, `preview_markdown`, `citations`.

### `POST /api/agents/conversations`
Creates a `conversation_id` for threading multiple chat calls.

### `GET /api/agents/chat/stream`
Server-sent events stream of the same payload as `/chat`.

---

## RAG ingestion
Semantic search over project descriptions/facilities:
```bash
python scripts/ingest_rag.py   # requires embeddings deployment
```

---

## Testing
```bash
pytest -q
```
Ensure `.env` is set and DB is migrated/seeded; some tests patch tools to avoid external calls.

---

## Troubleshooting
- **No key / 401**: ensure Azure/OpenAI env vars are set.
- **429 / rate limits**: slow down or use a different deployment/model.
- **Bad JSON in UI**: clear localStorage/API base; ensure backend is running.

---

## Deterministic alternative
Prefer a fixed, guardrailed workflow? Use the `feature/langgraph-tools` branch, which routes intent → SQL → detail/analysis via explicit LangGraph edges. README in that branch covers its specifics.
