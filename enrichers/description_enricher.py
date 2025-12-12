"""
Context Enricher for Semantic Search Over Property Descriptions

This enricher adds relevant property descriptions to the LLM context
for queries that need semantic search (e.g., "find luxury apartments with sea view").

Why Context Enricher vs Tool:
- Context Enricher: Automatically enriches EVERY query with relevant context (better for semantic search)
- Tool: Agent decides when to call it (might miss opportunities)

For semantic search over descriptions, Context Enricher is the right choice!
"""
from vann.core.context_enricher import ContextEnricher
from langchain_chroma import Chroma
from langchain_openai import OpenAIEmbeddings
from helpers.vectorstore import get_vectorstore
import logging

logger = logging.getLogger(__name__)


class PropertyDescriptionEnricher(ContextEnricher):
    """
    Enriches agent context with semantically similar property descriptions.
    
    How it works:
    1. User asks: "Find luxury waterfront apartments"
    2. This enricher searches property descriptions for relevant matches
    3. Adds top matches to LLM context
    4. LLM generates better SQL with understanding of qualitative features
    """
    
    def __init__(self, k: int = 3):
        """
        Initialize enricher.
        
        Args:
            k: Number of similar property descriptions to add as context
        """
        self.k = k
        try:
            self.vectorstore = get_vectorstore()
            logger.info("✅ Property Description Enricher initialized with RAG vectorstore")
        except Exception as e:
            logger.warning(f"⚠️  Could not initialize vectorstore: {e}")
            self.vectorstore = None
    
    async def enrich_context(self, messages: list, user_context: dict) -> list:
        """
        Enrich context with relevant property descriptions.
        
        Args:
            messages: Current conversation messages
            user_context: User metadata
        
        Returns:
            Enhanced messages with property description context
        """
        if not self.vectorstore:
            logger.debug("Vectorstore not available, skipping description enricher")
            return messages
        
        # Get the latest user message
        latest_message = next(
            (msg for msg in reversed(messages) if msg.get('role') == 'user'),
            None
        )
        
        if not latest_message:
            return messages
        
        query_text = latest_message.get('content', '')
        
        # Check if this is a qualitative query (needs semantic search)
        qualitative_keywords = [
            'luxury', 'modern', 'sea view', 'waterfront', 'spacious',
            'cozy', 'elegant', 'premium', 'exclusive', 'stunning',
            'panoramic', 'beachfront', 'pool', 'gym', 'amenities'
        ]
        
        is_qualitative = any(keyword in query_text.lower() for keyword in qualitative_keywords)
        
        if not is_qualitative:
            logger.debug(f"Query doesn't need semantic search: {query_text[:50]}...")
            return messages
        
        # Perform semantic search
        try:
            logger.info(f"🔍 Performing semantic search for: {query_text[:50]}...")
            
            docs = self.vectorstore.similarity_search(query_text, k=self.k)
            
            if docs:
                # Format property descriptions as context
                context_text = "\n\n**Relevant Properties (for qualitative understanding):**\n"
                for i, doc in enumerate(docs, 1):
                    context_text += f"{i}. {doc.page_content}\n"
                
                # Add as system message before latest user message
                enriched_messages = messages[:-1] + [
                    {
                        'role': 'system',
                        'content': context_text
                    },
                    latest_message
                ]
                
                logger.info(f"✅ Added {len(docs)} property descriptions to context")
                return enriched_messages
            else:
                logger.debug("No relevant descriptions found")
                return messages
                
        except Exception as e:
            logger.error(f"❌ Error in semantic search: {e}")
            return messages
