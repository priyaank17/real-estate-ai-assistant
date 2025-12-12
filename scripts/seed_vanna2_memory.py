"""
Vanna 2.0 Tool Memory Seeding (Optional)

Unlike Vanna 0.x, Vanna 2.0 learns automatically from successful queries.
This script is OPTIONAL - it just pre-seeds Tool Memory with examples
for better cold-start performance.

The agent will continue learning from real usage automatically.
"""
import os
import sys
import django
import asyncio

# Setup Django
sys.path.append(os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'silver_land.settings')
django.setup()

from vanna_agent import create_vanna_agent
from vanna.core.user import User


async def seed_tool_memory():
    """
    Pre-seed Tool Memory with example queries for better cold-start.
    
    In Vanna 2.0, this is OPTIONAL. The agent learns automatically
    from successful queries during normal usage.
    """
    print("🌱 Seeding Vanna 2.0 Tool Memory...")
    print("Note: This is optional - the agent learns automatically from usage!\n")
    
    agent = create_vanna_agent()
    
    # Create a demo user
    user = User(
        id="admin-seed",
        email="admin@example.com",
        group_memberships=['admin']
    )
    
    # Pre-seed with diverse example queries
    # These will be used as RAG context for similar future queries
    seed_queries = [
        "Find all apartments in Dubai",
        "Show me 2 bedroom villas",
        "Properties under 500000",
        "List 3 bedroom apartments",
        "Find villas in London",
        "Show properties with 4 bedrooms",
        "Search for townhouses",
        "Properties between 1000000 and 5000000",
        "Find the cheapest properties",
        "Show me luxury apartments",
    ]
    
    print("Executing seed queries to build Tool Memory...\n")
    
    for i, query in enumerate(seed_queries, 1):
        print(f"[{i}/{len(seed_queries)}] Processing: \"{query}\"")
        
        try:
            # Execute query - this will automatically save to Tool Memory
            result = await agent.execute(
                messages=[{"role": "user", "content": query}],
                user=user,
                conversation_id=f"seed-{i}"
            )
            
            if result.final_message:
                # Check if SQL was executed
                sql_executed = any(
                    hasattr(step, 'tool_name') and step.tool_name == 'run_sql'
                    for step in result.steps
                )
                
                if sql_executed:
                    print(f"  ✅ Saved to Tool Memory")
                else:
                    print(f"  ⚠️  No SQL executed (might be a follow-up)")
            
        except Exception as e:
            print(f"  ❌ Error: {str(e)}")
        
        print()
    
    print("=" * 60)
    print("✅ Tool Memory Seeding Complete!")
    print()
    print("What happens now:")
    print("1. Future similar queries will use these examples (RAG)")
    print("2. Agent continues learning from ALL successful queries")
    print("3. Tool Memory grows automatically with usage")
    print()
    print("Try it out:")
    print('  curl -X POST http://localhost:8000/api/vanna/chat \\')
    print('    -H "Content-Type: application/json" \\')
    print('    -d \'{"message": "Show me 2 bedroom apartments"}\'')
    print("=" * 60)


if __name__ == "__main__":
    print("""
╔══════════════════════════════════════════════════════════════╗
║         Vanna 2.0 Tool Memory Seeding (Optional)             ║
╚══════════════════════════════════════════════════════════════╝

This script pre-seeds Tool Memory with example queries.

🔥 KEY DIFFERENCE FROM VANNA 0.x:
   - Vanna 0.x: Manual training was REQUIRED
   - Vanna 2.0: Auto-learning from usage (this is OPTIONAL)

Why seed?
  ✅ Better accuracy on first queries
  ✅ Faster cold-start performance

Why skip?
  ✅ Agent learns from real queries automatically
  ✅ Less setup required

Your choice! The agent works either way.
""")
    
    choice = input("Seed Tool Memory? (y/n): ").lower().strip()
    
    if choice == 'y':
        asyncio.run(seed_tool_memory())
    else:
        print("\n✅ Skipping seeding - agent will learn from real usage!")
        print("Start the server and queries will be learned automatically.")
