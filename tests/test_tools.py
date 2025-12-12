import os
import sys
import django
import pandas as pd
from django.test import TestCase
from unittest.mock import patch, MagicMock

# Setup Django
sys.path.append(os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'silver_land.settings')
django.setup()

from tools.ui_tool import update_ui_context
from tools.sql_tool import execute_sql_query
from tools.rag_tool import search_rag

class ToolTests(TestCase):
    def setUp(self):
        os.environ["OPENAI_API_KEY"] = "dummy"

    def test_ui_tool(self):
        """Test that the UI tool returns the expected string."""
        result = update_ui_context.invoke({"shortlisted_project_ids": [1, 2, 3]})
        self.assertEqual(result, "UI Context Updated.")

    @patch("tools.sql_tool.get_vanna_client")
    def test_sql_tool(self, mock_get_vanna):
        """Test SQL tool with mocked Vanna client."""
        df = pd.DataFrame(
            [
                {"id": "1", "name": "Project A", "price": 100000, "city": "Dubai"},
                {"id": "2", "name": "Project B", "price": 200000, "city": "Dubai"},
            ]
        )
        mock_vn = MagicMock()
        mock_vn.generate_sql.return_value = "SELECT * FROM projects"
        mock_vn.run_sql.return_value = df
        mock_get_vanna.return_value = mock_vn
        
        result = execute_sql_query.invoke("Find projects")
        self.assertEqual(result["sql"], "SELECT * FROM projects")
        self.assertEqual(result["row_count"], 2)
        self.assertFalse(result["truncated"])
        self.assertEqual(result["project_ids"], ["1", "2"])
        self.assertEqual(result["rows"][0]["name"], "Project A")
        self.assertIn("Project A", result["preview_markdown"])

    @patch("tools.rag_tool.get_vectorstore")
    def test_rag_tool(self, mock_get_vectorstore):
        """Test RAG tool with mocked VectorStore."""
        mock_store = MagicMock()
        mock_doc = MagicMock()
        mock_doc.metadata = {
            "project_name": "Test Project",
            "project_id": "123",
            "city": "Dubai",
            "property_type": "apartment",
        }
        mock_doc.page_content = "A nice place with a pool."
        mock_store.similarity_search.return_value = [mock_doc]
        mock_get_vectorstore.return_value = mock_store
        
        result = search_rag.invoke("Find nice place")
        self.assertIn("results", result)
        self.assertEqual(result["project_ids"], ["123"])
        self.assertEqual(result["results"][0]["project_id"], "123")
        self.assertIn("Test Project", result["preview_markdown"])
