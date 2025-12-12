"""
Vanna 2.0 Agent Setup - Using Official API

Following official Vanna docs: https://vanna.ai/docs/configure/openai/sqlite
"""
import os
import logging

# Official Vanna imports (from docs)
from vanna import Agent
from vanna.core.registry import ToolRegistry
from vanna.core.user import UserResolver, User, RequestContext
from vanna.tools import RunSqlTool
from vanna.tools.agent_memory import (
    SaveQuestionToolArgsTool,
    SearchSavedCorrectToolUsesTool,
    SaveTextMemoryTool
)
from vanna.integrations.openai import OpenAILlmService
from vanna.integrations.sqlite import SqliteRunner
from vanna.integrations.local.agent_memory import DemoAgentMemory

from django.conf import settings

# Import our custom tools
from tools_vanna.investment_tool_vanna import InvestmentToolVanna
from tools_vanna.comparison_tool_vanna import ComparisonToolVanna
from tools_vanna.booking_tool_vanna import BookingToolVanna
from tools_vanna.similarity_tool_vanna import FindSimilarPropertiesTool
from monitoring.vanna_monitor import get_monitor

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class SimpleUserResolver(UserResolver):
    """
    Simple user resolver for demo purposes.
    In production, integrate with your auth system.
    """
    async def resolve_user(self, request_context: RequestContext) -> User:
        # For demo, create a simple user
        # In production, decode JWT, check session, etc.
        user_id = request_context.get_header('X-User-ID') or 'demo-user'
        
        logger.info(f"👤 User resolved: {user_id}")
        
        return User(
            id=user_id,
            email=f"{user_id}@example.com",
            group_memberships=['user']  # All users can query
        )


def create_vanna_agent():
    """
    Factory function to create Vanna 2.0 agent.
    Based on official docs: https://vanna.ai/docs/configure/openai/sqlite
    
    Returns:
        Agent: Configured Vanna agent
    """
    logger.info("🚀 Initializing Vanna 2.0 Agent...")
    
    # Initialize monitor
    monitor = get_monitor(log_file="logs/vanna_monitor.log")
    logger.info("✅ Monitoring initialized")
    
    # 1. Configure LLM (following official docs)
    llm = OpenAILlmService(
        model="gpt-4o-mini",
        api_key=os.getenv("OPENAI_API_KEY")
    )
    logger.info("✅ LLM configured: gpt-4o-mini")
    
    # 2. Configure database tool (following official docs)
    db_path = settings.DATABASES['default']['NAME']
    db_tool = RunSqlTool(
        sql_runner=SqliteRunner(database_path=db_path)
    )
    logger.info(f"✅ Database configured: {db_path}")
    
    # 3. Configure agent memory (following official docs)
    agent_memory = DemoAgentMemory(max_items=1000)
    logger.info("✅ Agent Memory initialized")
    
    # 4. Configure user authentication (following official docs)
    user_resolver = SimpleUserResolver()
    logger.info("✅ User Resolver configured")
    
    # 5. Create tool registry and register tools (following official docs)
    tools = ToolRegistry()
    
    # Register database tool
    tools.register_local_tool(db_tool, access_groups=['admin', 'user'])
    
    # Register agent memory tools (following official docs)
    tools.register_local_tool(
        SaveQuestionToolArgsTool(),
        access_groups=['admin']
    )
    tools.register_local_tool(
        SearchSavedCorrectToolUsesTool(),
        access_groups=['admin', 'user']
    )
    tools.register_local_tool(
        SaveTextMemoryTool(),
        access_groups=['admin', 'user']
    )
    
    # Register our custom business tools
    tools.register_local_tool(InvestmentToolVanna(), access_groups=['user', 'admin'])
    tools.register_local_tool(ComparisonToolVanna(), access_groups=['user', 'admin'])
    tools.register_local_tool(BookingToolVanna(), access_groups=['user', 'admin'])
    tools.register_local_tool(FindSimilarPropertiesTool(), access_groups=['user', 'admin'])
    
    logger.info("✅ All tools registered (8 total)")
    
    # 6. Create agent (following official docs)
    agent = Agent(
        llm_service=llm,
        tool_registry=tools,
        user_resolver=user_resolver,
        agent_memory=agent_memory
    )
    
    logger.info("=" * 60)
    logger.info("✅ VANNA 2.0 AGENT INITIALIZED SUCCESSFULLY")
    logger.info("=" * 60)
    logger.info("Features enabled:")
    logger.info("  ✅ Text-to-SQL with Tool Memory")
    logger.info("  ✅ Conversational Memory")
    logger.info("  ✅ Investment Analysis")
    logger.info("  ✅ Property Comparison")
    logger.info("  ✅ Booking Viewings")
    logger.info("  ✅ Cross-Selling / Similarity Matching")
    logger.info("  ✅ Monitoring & Logging")
    logger.info("=" * 60)
    
    return agent
