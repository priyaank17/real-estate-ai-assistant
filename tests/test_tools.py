import os
import sys
import django
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
        mock_vn = MagicMock()
        mock_vn.generate_sql.return_value = "SELECT * FROM projects"
        mock_vn.run_sql.return_value = MagicMock(empty=False, to_markdown=lambda index: "| Project | Price |\n|---|---|\n| A | 100 |")
        mock_get_vanna.return_value = mock_vn
        
        result = execute_sql_query.invoke("Find projects")
        self.assertIn("| Project | Price |", result)

    @patch("tools.rag_tool.get_vectorstore")
    def test_rag_tool(self, mock_get_vectorstore):
        """Test RAG tool with mocked VectorStore."""
        mock_store = MagicMock()
        mock_doc = MagicMock()
        mock_doc.metadata = {"project_name": "Test Project"}
        mock_doc.page_content = "A nice place."
        mock_store.similarity_search.return_value = [mock_doc]
        mock_get_vectorstore.return_value = mock_store
        
        result = search_rag.invoke("Find nice place")
        self.assertIn("Test Project", result)
        self.assertIn("A nice place", result)
