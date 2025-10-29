import logging
import httpx
from typing import List, AsyncGenerator, Optional
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, BaseMessage
from app.models import Article
from app.config import settings

logger = logging.getLogger(__name__)

class LLMService:
    """Service for generating LLM responses with source citations and conversation history
    
    Supports multiple LLM providers:
    - Ollama (local, free) - default if running
    - OpenAI (cloud, requires API key) - fallback option
    """
    
    def __init__(self):
        self.provider = None
        self.langchain_llm = None
        self._initialize_llm()
    
    def _check_ollama_health(self) -> bool:
        """Check if Ollama is running and accessible
        
        Returns:
            True if Ollama is running, False otherwise
        """
        try:
            response = httpx.get(f"{settings.ollama_base_url}/api/tags", timeout=2.0)
            return response.status_code == 200
        except Exception as e:
            logger.debug(f"Ollama health check failed: {e}")
            return False
    
    def _initialize_llm(self):
        """Initialize the LLM based on provider settings with smart auto-detection"""
        provider = settings.llm_provider.lower()
        
        # Auto-detection mode: try Ollama first, then OpenAI
        if provider == "auto":
            if self._check_ollama_health():
                logger.info("🤖 Auto-detected Ollama running locally")
                self._setup_ollama()
                return
            elif settings.openai_api_key:
                logger.info("🔑 Ollama not available, falling back to OpenAI")
                self._setup_openai()
                return
            else:
                raise RuntimeError(
                    "❌ No LLM provider available!\n"
                    "Options:\n"
                    "  1. Install Ollama: https://ollama.com/download\n"
                    "  2. Set OPENAI_API_KEY in .env file"
                )
        
        # Explicit provider selection
        elif provider == "ollama":
            if not self._check_ollama_health():
                raise RuntimeError(
                    f"❌ Ollama not running at {settings.ollama_base_url}\n"
                    "Run: ollama serve"
                )
            self._setup_ollama()
        
        elif provider == "openai":
            if not settings.openai_api_key:
                raise RuntimeError(
                    "❌ OpenAI API key not configured\n"
                    "Set OPENAI_API_KEY in .env file"
                )
            self._setup_openai()
        
        else:
            raise ValueError(f"Unknown LLM provider: {provider}")
    
    def _setup_ollama(self):
        """Initialize Ollama LLM"""
        try:
            from langchain_ollama import ChatOllama
            
            self.langchain_llm = ChatOllama(
                model=settings.ollama_model,
                base_url=settings.ollama_base_url,
                temperature=settings.ollama_temperature,
                num_predict=settings.ollama_max_tokens,
            )
            self.provider = "ollama"
            logger.info(f"✅ Initialized Ollama with model: {settings.ollama_model}")
        except ImportError:
            raise RuntimeError(
                "❌ langchain-ollama not installed\n"
                "Run: pip install langchain-ollama"
            )
    
    def _setup_openai(self):
        """Initialize OpenAI LLM"""
        try:
            from langchain_openai import ChatOpenAI
            
            self.langchain_llm = ChatOpenAI(
                model=settings.openai_model,
                temperature=settings.openai_temperature,
                max_tokens=settings.openai_max_tokens,
                streaming=True,
                api_key=settings.openai_api_key
            )
            self.provider = "openai"
            logger.info(f"✅ Initialized OpenAI with model: {settings.openai_model}")
        except ImportError:
            raise RuntimeError(
                "❌ langchain-openai not installed\n"
                "Run: pip install langchain-openai"
            )
    
    def get_provider_info(self) -> dict:
        """Get information about the current LLM provider
        
        Returns:
            Dictionary with provider details
        """
        if self.provider == "ollama":
            return {
                "provider": "ollama",
                "model": settings.ollama_model,
                "base_url": settings.ollama_base_url,
                "cost": "free"
            }
        elif self.provider == "openai":
            return {
                "provider": "openai",
                "model": settings.openai_model,
                "cost": "paid"
            }
        return {"provider": "unknown"}
    
    def _build_context_message(self, articles: List[Article]) -> str:
        """Build context message with article information
        
        Args:
            articles: List of relevant articles
            
        Returns:
            Formatted context string
        """
        if not articles:
            return "No relevant articles found in the database."
        
        context_lines = ["Here are the relevant crypto news articles you must use to answer:\n"]
        
        # For Ollama, use more concise context to avoid overwhelming smaller models
        # For OpenAI, we can use more content
        max_content_length = 400 if self.provider == "ollama" else 500
        
        for i, article in enumerate(articles, 1):
            date_str = article.published_date.strftime("%b %d, %Y") if article.published_date else "Unknown"
            context_lines.append(f"=== [Article {i}] ===")
            context_lines.append(f"Title: {article.title}")
            context_lines.append(f"Source: {article.source} ({date_str})")
            context_lines.append(f"URL: {article.url}")
            
            # Clean and truncate content
            content = article.content[:max_content_length] if article.content else "No content"
            content = content.strip()
            context_lines.append(f"Content: {content}...")
            context_lines.append("")  # Empty line between articles
        
        return "\n".join(context_lines)
    
    def _build_system_prompt(self) -> str:
        """Build the system prompt for the LLM
        
        Returns:
            System prompt string
        """
        return """You are a crypto news analyst assistant. You MUST follow these rules strictly:

CRITICAL RULES:
1. ONLY use information from the provided articles in the context. DO NOT use external knowledge.
2. If the question cannot be answered from the provided articles, say "I don't have information about that in the recent news articles."
3. NEVER make up or infer information that is not explicitly stated in the articles.

CITATION FORMAT (MANDATORY):
- You MUST cite every fact using this EXACT format: "According to [Article N]..."
- Replace N with the article number (1, 2, 3, etc.)
- Include the source name and date: "According to [Article 1] from CoinTelegraph (Jan 20, 2025)"
- Example: "According to [Article 2] from TheDefiant (Oct 28, 2025), Bitcoin reached $70,000."

RESPONSE STRUCTURE:
1. Start with a direct answer to the question
2. Provide supporting details from the articles with proper citations
3. If multiple articles mention the same topic, cite all relevant ones
4. Be concise - focus on the most relevant information
5. DO NOT include a "Sources:" section - sources are displayed separately by the interface

WHAT TO AVOID:
- DO NOT answer questions about topics not covered in the provided articles
- DO NOT provide general crypto knowledge unless it's in the articles
- DO NOT make predictions or give opinions
- DO NOT forget to cite sources for EVERY claim

Remember: Every single fact or claim you make MUST have a citation to a specific article number."""
    
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
                yield "Please try a different query or refine your search terms."
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
            
            # Stream response from LLM (works with both Ollama and OpenAI)
            chunk_count = 0
            full_response = ""
            
            async for chunk in self.langchain_llm.astream(messages):
                if chunk.content:
                    chunk_count += 1
                    full_response += chunk.content
                    logger.debug(f"Chunk {chunk_count}: {len(chunk.content)} chars")
                    yield chunk.content
            
            logger.info(
                f"LLM streaming complete ({self.provider}): "
                f"{chunk_count} chunks, {len(full_response)} chars total"
            )
        
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
