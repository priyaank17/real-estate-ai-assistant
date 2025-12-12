import os
import sys
import django
from django.test import TestCase, Client
from unittest.mock import patch, MagicMock, AsyncMock
from langchain_core.messages import AIMessage

# Setup Django
sys.path.append(os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'silver_land.settings')
django.setup()

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
