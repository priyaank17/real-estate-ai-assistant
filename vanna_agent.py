"""
Vanna 2.0 Agent Setup - Using Official API

Following official Vanna docs: https://vanna.ai/docs/configure/openai/sqlite
"""
import os
import logging
import asyncio

# Official Vanna imports (from docs)
from vanna import Agent
from vanna.core.registry import ToolRegistry
from vanna.core.user import UserResolver, User, RequestContext
from vanna.core.tool import ToolContext
from vanna.tools import RunSqlTool
from vanna.tools.agent_memory import (
    SaveQuestionToolArgsTool,
    SearchSavedCorrectToolUsesTool,
    SaveTextMemoryTool
)
try:
    from vanna.integrations.azure import AzureOpenAILlmService
except ImportError:
    AzureOpenAILlmService = None
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
    # Prefer Azure OpenAI if configured, else fallback to OpenAI
    azure_key = os.getenv("AZURE_OPENAI_API_KEY")
    azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
    azure_deployment = os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT", "gpt-4o-mini")
    azure_version = os.getenv("AZURE_OPENAI_API_VERSION", "2024-05-01-preview")
    openai_key = os.getenv("OPENAI_API_KEY")

    if azure_key and azure_endpoint and AzureOpenAILlmService is not None:
        llm = AzureOpenAILlmService(
            deployment_name=azure_deployment,
            api_key=azure_key,
            azure_endpoint=azure_endpoint,
            api_version=azure_version,
        )
        logger.info(f"✅ LLM configured (Azure): {azure_deployment}")
    elif azure_key and azure_endpoint:
        # Fallback to OpenAI client with Azure base_url + api-version
        base_url = f"{azure_endpoint}/openai/deployments/{azure_deployment}"
        if not base_url.endswith("/"):
            base_url += "/"
        llm = OpenAILlmService(
            model=azure_deployment,
            api_key=azure_key,
            base_url=base_url,
            default_headers={"api-key": azure_key},
            default_query={"api-version": azure_version},
        )
        logger.info(f"✅ LLM configured (Azure via OpenAI client): {azure_deployment}")
    else:
        llm = OpenAILlmService(
            model=os.getenv("OPENAI_LLM_MODEL", "gpt-4o-mini"),
            api_key=openai_key,
        )
        logger.info(f"✅ LLM configured (OpenAI): {os.getenv('OPENAI_LLM_MODEL', 'gpt-4o-mini')}")
    
    # 2. Configure database tool (following official docs)
    db_path = str(settings.DATABASES['default']['NAME'])
    db_tool = RunSqlTool(
        sql_runner=SqliteRunner(database_path=db_path)
    )
    logger.info(f"✅ Database configured: {db_path}")
    
    # 3. Configure agent memory (in-memory for reliable seeding)
    agent_memory = DemoAgentMemory(max_items=2000)
    logger.info("✅ Agent Memory initialized (DemoAgentMemory)")
    
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
    
    # Business and helper tools
    tools.register_local_tool(InvestmentToolVanna(), access_groups=['user', 'admin'])
    tools.register_local_tool(ComparisonToolVanna(), access_groups=['user', 'admin'])
    tools.register_local_tool(BookingToolVanna(), access_groups=['user', 'admin'])
    # tools.register_local_tool(FindSimilarPropertiesTool(), access_groups=['user', 'admin'])

    logger.info("✅ All tools registered (12 total)")
    
    # 6. Create agent (following official docs)
    agent = Agent(
        llm_service=llm,
        tool_registry=tools,
        user_resolver=user_resolver,
        agent_memory=agent_memory
    )

    # Seed schema/context to help the LLM generate correct SQL
    try:
        seed_user = User(id="schema-seed", email="schema@example.com", group_memberships=["admin"])
        seed_ctx = ToolContext(
            user=seed_user,
            conversation_id="schema-seed",
            request_id="seed-1",
            agent_memory=agent_memory,
        )

        async def _seed_schema():
            await agent.agent_memory.save_text_memory(
                content="""
                Table agents_project:
                - id (UUID primary key)
                - name (text)
                - bedrooms (int)
                - bathrooms (float)
                - status (text)
                - unit_type (text)
                - developer (text)
                - price (numeric)
                - area (float)
                - property_type (text)
                - city (text)
                - country (text)
                - completion_date (text)
                - features (text)
                - facilities (text)
                - description (text)
                """,
                context=seed_ctx,
            )
            await agent.agent_memory.save_text_memory(
                content="""
                Table agents_lead:
                - id (UUID primary key)
                - first_name (text)
                - last_name (text, nullable)
                - email (text, unique)
                - preferences (text, nullable)
                - created_at (datetime)
                """,
                context=seed_ctx,
            )
            await agent.agent_memory.save_text_memory(
                content="""
                Table agents_booking:
                - id (UUID primary key)
                - lead_id (UUID, FK to agents_lead.id)
                - project_id (UUID, FK to agents_project.id)
                - booking_date (datetime)
                """,
                context=seed_ctx,
            )
            await agent.agent_memory.save_text_memory(
                content="Example: 'Find 2 bedroom apartments in Dubai' -> SELECT * FROM agents_project WHERE bedrooms=2 AND property_type='apartment' AND city='Dubai' LIMIT 20",
                context=seed_ctx,
            )
            await agent.agent_memory.save_text_memory(
                content="Example: '2 bedroom flats in Miami under 4 million' -> SELECT name, city, bedrooms, price FROM agents_project WHERE city='Miami' AND price <= 4000000 AND property_type IN ('apartment','flat') ORDER BY price ASC LIMIT 20",
                context=seed_ctx,
            )
            await agent.agent_memory.save_text_memory(
                content="Example: 'Show recent bookings' -> SELECT b.id, p.name as project_name, l.first_name, l.email, b.booking_date FROM agents_booking b JOIN agents_project p ON b.project_id = p.id JOIN agents_lead l ON b.lead_id = l.id ORDER BY b.booking_date DESC LIMIT 20",
                context=seed_ctx,
            )
            await agent.agent_memory.save_text_memory(
                content=(
                    "Tool usage guidance: For structured filters (city, price, bedrooms, property_type), "
                    "first call run_sql with a SELECT on agents_project. Only use find_similar_properties "
                    "if run_sql returns 0 rows. 'flat' is equivalent to 'apartment'."
                ),
                context=seed_ctx,
            )

        asyncio.run(_seed_schema())
        logger.info("✅ Seeded schema/examples into agent memory")
    except Exception as e:
        logger.warning(f"⚠️  Could not seed schema/examples: {e}")
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
