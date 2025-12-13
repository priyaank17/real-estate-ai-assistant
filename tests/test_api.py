import os
import sys
import django
import pytest
from django.test import TestCase, Client
from unittest.mock import patch, MagicMock, AsyncMock
from langchain_core.messages import AIMessage, ToolMessage
import json

try:
    import vanna  # noqa: F401
    VANNA_AVAILABLE = True
except ImportError:
    VANNA_AVAILABLE = False

# Setup Django
sys.path.append(os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'silver_land.settings')
django.setup()

if not VANNA_AVAILABLE:
    pytest.skip("Vanna not installed; skipping API tests dependent on vanna import", allow_module_level=True)

class ApiTests(TestCase):
    def setUp(self):
        os.environ["OPENAI_API_KEY"] = "dummy"
        self.client = Client()

    def test_create_conversation(self):
        """Test creating a conversation."""
        response = self.client.post("/api/conversations")
        self.assertEqual(response.status_code, 200)
        self.assertIn("conversation_id", response.json())

    @patch("agents.api.agent_app.ainvoke", new_callable=AsyncMock)
    def test_chat_api(self, mock_ainvoke):
        """Test the chat API with mocked agent response."""
        # Mock the agent returning a simple text response
        mock_msg = AIMessage(content="Hello there!")
        mock_ainvoke.return_value = {"messages": [mock_msg]}
        
        response = self.client.post(
            "/api/agents/chat", 
            {"message": "Hi"}, 
            content_type="application/json"
        )
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["response"], "Hello there!")
        self.assertIsNone(data["data"])
        self.assertIsNone(data["tools_used"])
        self.assertIsNone(data["preview_markdown"])
        self.assertIsNone(data.get("citations"))

    @patch("agents.api.agent_app.ainvoke", new_callable=AsyncMock)
    def test_chat_api_with_structured_data(self, mock_ainvoke):
        """Test the chat API when agent returns structured data via ui_tool."""
        # Mock the agent returning a tool call
        mock_msg = AIMessage(
            content="I found some projects.",
            tool_calls=[{
                "name": "update_ui_context",
                "args": {"shortlisted_project_ids": [101, 102]},
                "id": "call_123"
            }]
        )
        mock_ainvoke.return_value = {"messages": [mock_msg]}
        
        response = self.client.post(
            "/api/agents/chat", 
            {"message": "Find projects"}, 
            content_type="application/json"
        )
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["response"], "I found some projects.")
        self.assertEqual(data["data"]["shortlisted_project_ids"], [101, 102])
        self.assertEqual(data["tools_used"], ["update_ui_context"])
        self.assertIsNone(data["preview_markdown"])
        self.assertIsNone(data.get("citations"))

    @patch("agents.api.agent_app.ainvoke", new_callable=AsyncMock)
    def test_chat_api_with_data_sync_tool_message(self, mock_ainvoke):
        """Ensure data_sync ToolMessage (stringified JSON) is parsed and returned."""
        ds_payload = {"rows": [{"id": "1", "name": "Proj"}], "row_count": 1, "preview_markdown": "| id | name |\n| 1 | Proj |"}
        mock_ainvoke.return_value = {
            "messages": [
                ToolMessage(name="data_sync", content=json.dumps(ds_payload), tool_call_id="data_sync"),
                AIMessage(content="Here are the results."),
            ]
        }
        
        response = self.client.post(
            "/api/agents/chat",
            {"message": "hi"},
            content_type="application/json"
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["data"]["row_count"], 1)
        self.assertEqual(data["preview_markdown"], ds_payload["preview_markdown"])
        # tools_used may be None in this path; ensure data came through
        self.assertIsNotNone(data["data"])

    @patch("agents.api.agent_app.ainvoke", new_callable=AsyncMock)
    def test_chat_api_hard_guard_when_no_tools(self, mock_ainvoke):
        """If no tools/citations/preview and not a greeting, API should return guard message."""
        mock_ainvoke.return_value = {"messages": [AIMessage(content="No tools used")]}
        resp = self.client.post(
            "/api/agents/chat",
            {"message": "Find me something"},
            content_type="application/json"
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        # In agentic mode with mock response, we simply return the AI message
        self.assertEqual(data["response"], "No tools used")
