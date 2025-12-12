# Silver Land Properties AI Assistant

Production-grade real estate AI agent with local LLM (Ollama), MCP tools, and hybrid search.

## 📁 Project Structure

```
real-estate-ai-assistant/
├── agents/                    # Django app (web layer only)
│   ├── __init__.py
│   ├── models.py             # Django models (Project, Lead, Booking)
│   ├── api.py                # REST API endpoints (uses MCP client)
│   ├── graph.py              # LangGraph agent definition
│   ├── apps.py
│   ├── admin.py
│   └── migrations/
│
├── tools/                     # Business logic tools (LangChain tools)
│   ├── __init__.py
│   ├── sql_tool.py           # Text-to-SQL (uses helpers.vanna)
│   ├── rag_tool.py           # Semantic search (uses helpers.vectorstore)
│   ├── booking_tool.py       # Property viewing bookings
│   ├── investment_tool.py    # ROI/yield calculations
│   ├── comparison_tool.py    # Side-by-side comparisons
│   ├── ui_tool.py            # UI context updates
│   └── web_tool.py           # Web search
│
├── helpers/                   # Utilities, clients, adapters
│   ├── __init__.py
│   ├── vanna.py              # Vanna client singleton
│   └── vectorstore.py        # ChromaDB vectorstore + embeddings
│
├── mcp/                       # MCP server (separate service)
│   ├── __init__.py
│   └── server.py             # FastMCP server (exposes tools)
│
├── scripts/                   # Setup & maintenance
│   ├── vanna_setup.py        # Train Vanna (one-time)
│   ├── ingest_rag.py         # Ingest RAG data (one-time)
│   └── seed_database.py      # Seed DB from CSV
│
├── data/                      # Data files
│   └── properties.csv        # 17k+ property listings
│
├── tests/                     # Test suite
│   ├── __init__.py
│   ├── test_tools.py         # Unit tests
│   └── test_api.py           # Integration tests
│
├── silver_land/               # Django settings
│   ├── settings.py
│   ├── urls.py
│   ├── wsgi.py
│   └── asgi.py
│
├── chroma_rag/               # RAG vector DB (gitignored)
├── chroma_vanna/             # Vanna index (gitignored)
├── db.sqlite3                # SQLite database (gitignored)
├── manage.py
├── requirements.txt
├── .gitignore
└── README.md
```

## 🎯 Architecture Highlights

### Clean Separation of Concerns

| Layer | Directory | Purpose | Examples |
|-------|-----------|---------|----------|
| **Web** | `agents/` | Django app, API, ORM models | api.py, models.py, graph.py |
| **Business Logic** | `tools/` | LangChain tools (@tool decorator) | sql_tool.py, rag_tool.py |
| **Helpers** | `helpers/` | Clients, adapters, utilities | vanna.py, vectorstore.py |
| **MCP Service** | `mcp/` | Tool exposure via MCP | server.py |
| **Scripts** | `scripts/` | CLI utilities, setup | seed_database.py |

### Why Helpers?

**Before:**
```python
# tools/rag_tool.py (mixed)
def get_vectorstore():  # ← Helper function
    ...

@tool
def search_rag():  # ← Actual tool
    ...
```

**After:**
```python
# helpers/vectorstore.py (pure helper)
def get_vectorstore():
    ...

# tools/rag_tool.py (pure tool)
from helpers.vectorstore import get_vectorstore

@tool
def search_rag():
    vectorstore = get_vectorstore()
    ...
```

**Benefits:**
- ✅ Tools are pure business logic
- ✅ Helpers are reusable across multiple tools
- ✅ Easy to mock helpers in tests
- ✅ Follows Single Responsibility Principle

## 🚀 Quick Start

### 1. Prerequisites
- Python 3.12+
- Ollama installed ([download](https://ollama.ai/download))

### 2. Install & Setup
```bash
# Clone repo
cd real-estate-ai-assistant

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Pull Ollama models
ollama pull llama3.1         # ~4.7GB
ollama pull nomic-embed-text # ~274MB
```

### 3. Initialize Database
```bash
# Run migrations
python manage.py migrate

# Seed from CSV (17k+ properties)
python scripts/seed_database.py
```

### 4. Train AI Components
```bash
# Train Vanna (Text-to-SQL)
python scripts/vanna_setup.py

# Ingest RAG data
python scripts/ingest_rag.py
```

### 5. Run Application
```bash
# Start Django server (automatically connects to MCP)
python manage.py runserver 8000
```

## 🔧 Architecture

### MCP Client Pattern
```
API → MultiServerMCPClient → MCP Server → Tools → Helpers
```

**Data Flow:**
1. User sends request to **REST API** (`agents/api.py`)
2. API uses **MCP Client** to connect to MCP server
3. **MCP Server** (`mcp/server.py`) exposes tools
4. **Tools** (`tools/`) contain business logic
5. **Helpers** (`helpers/`) provide shared utilities
6. Results flow back to user

## 📡 API Usage

### Chat Endpoint
**POST** `/api/agents/chat`

```json
{
  "message": "Find 2 bedroom apartments in Dubai under 500k"
}
```

**Response:**
```json
{
  "response": "I found 3 apartments...",
  "conversation_id": "<uuid>",
  "data": {
    "shortlisted_project_ids": [101, 102, 103]
  }
}
```

## 🧪 Testing

```bash
# Run all tests
python manage.py test tests

# Run specific tests
python manage.py test tests.test_tools
```

## 🛠️ Development

### Adding a New Tool

1. **Create tool** in `tools/new_tool.py`:
```python
from langchain_core.tools import tool
from helpers.vanna import get_vanna_client  # Use helpers

@tool
def my_new_tool(query: str) -> str:
    """Tool description."""
    vn = get_vanna_client()
    return vn.query(query)
```

2. **Expose** in `mcp/server.py`:
```python
from tools.new_tool import my_new_tool

@mcp.tool()
def my_new_tool_mcp(query: str) -> str:
    return my_new_tool.invoke(query)
```

3. **Restart** server

### Adding a New Helper

1. Create file in `helpers/my_helper.py`
2. Import in tools: `from helpers.my_helper import ...`
3. Use across multiple tools

## 🎯 Performance

### Ollama vs OpenAI

| Metric | Ollama (Local) | OpenAI (Cloud) |
|--------|----------------|----------------|
| Cost | $0 (Free) | ~$0.03/request |
| Privacy | 100% Local | Data sent to API |
| Speed | Slower | Faster |
| Internet | Not required | Required |

### Recommended Hardware
- **Minimum**: 8GB RAM, 4-core CPU
- **Recommended**: 16GB RAM, 8-core CPU
- **Storage**: ~10GB for models + data

---

**Built with LangGraph, Django Ninja, Ollama, and MCP**
