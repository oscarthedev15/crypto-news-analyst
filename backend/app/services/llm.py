import logging
from typing import List, AsyncGenerator, Optional
from openai import AsyncOpenAI
from langchain.chat_models import init_chat_model
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, BaseMessage
from app.models import Article
from app.config import settings

logger = logging.getLogger(__name__)

class LLMService:
    """Service for generating LLM responses with source citations and conversation history"""
    
    def __init__(self):
        self.client = AsyncOpenAI(api_key=settings.openai_api_key)
        # Use LangChain v1 init_chat_model for unified model initialization
        self.langchain_llm = init_chat_model(
            model="openai:gpt-4o-mini",
            temperature=0.5,
            max_tokens=800,
            streaming=True,
            api_key=settings.openai_api_key
        )
    
    def _build_context_message(self, articles: List[Article]) -> str:
        """Build context message with article information
        
        Args:
            articles: List of relevant articles
            
        Returns:
            Formatted context string
        """
        if not articles:
            return "No relevant articles found in the database."
        
        context_lines = ["Here are the relevant crypto news articles:\n"]
        
        for i, article in enumerate(articles, 1):
            date_str = article.published_date.strftime("%b %d, %Y") if article.published_date else "Unknown"
            context_lines.append(f"[Article {i}]")
            context_lines.append(f"Title: {article.title}")
            context_lines.append(f"Source: {article.source} ({date_str})")
            context_lines.append(f"URL: {article.url}")
            content_preview = article.content[:500] if article.content else "No content"
            context_lines.append(f"Content: {content_preview}...")
            context_lines.append("")
        
        return "\n".join(context_lines)
    
    def _build_system_prompt(self) -> str:
        """Build the system prompt for the LLM
        
        Returns:
            System prompt string
        """
        return """You are a crypto news analyst assistant. Follow these rules:
1. Answer ONLY based on the provided articles in the current context
2. ALWAYS cite your sources using the format: "According to [Article N]..."
3. Include the source name and date when citing (e.g., "According to [Article 1] from CoinTelegraph (Jan 20, 2025)")
4. Use multiple citations if information comes from multiple articles
5. Be concise but thorough in your response
6. If the articles don't contain enough information to answer the question, clearly state that
7. Maintain conversation context - refer back to previous messages when relevant
8. At the end of your response, provide a "Sources:" section listing the article URLs you used"""
    
    async def generate_streaming_response(
        self,
        question: str,
        articles: List[Article],
        chat_history: Optional[List[BaseMessage]] = None
    ) -> AsyncGenerator[str, None]:
        """Generate streaming LLM response with citations and conversation history
        
        Args:
            question: User's question
            articles: List of relevant articles
            chat_history: Optional list of previous messages for context
            
        Yields:
            Text chunks of the response
        """
        try:
            # Handle no articles case
            if not articles:
                yield "I apologize, but I couldn't find relevant articles in our database to answer this question. "
                yield "Please try a different query or try the web search feature for live internet search."
                return
            
            # Build context with articles
            context = self._build_context_message(articles)
            
            # Build messages list
            messages = [SystemMessage(content=self._build_system_prompt())]
            
            # Add chat history if provided
            if chat_history:
                messages.extend(chat_history)
                logger.debug(f"Added {len(chat_history)} messages from chat history")
            
            # Add current context and question
            user_message = f"{context}\n\nUser Question: {question}"
            messages.append(HumanMessage(content=user_message))
            
            # Call OpenAI API with streaming using LangChain v1
            chunk_count = 0
            full_response = ""
            
            async for chunk in self.langchain_llm.astream(messages):
                if chunk.content:
                    chunk_count += 1
                    full_response += chunk.content
                    logger.debug(f"Chunk {chunk_count}: {len(chunk.content)} chars")
                    yield chunk.content
            
            logger.info(f"LLM streaming complete: {chunk_count} chunks, {len(full_response)} chars total")
        
        except Exception as e:
            logger.error(f"Error generating LLM response: {e}")
            yield f"Error generating response: {str(e)}"


# Singleton instance
_llm_service = None

def get_llm_service() -> LLMService:
    """Get or create the LLM service singleton"""
    global _llm_service
    if _llm_service is None:
        _llm_service = LLMService()
    return _llm_service
