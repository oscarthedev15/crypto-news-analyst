import logging
from typing import List, AsyncGenerator
from openai import AsyncOpenAI
from app.models import Article
from app.config import settings

logger = logging.getLogger(__name__)

class LLMService:
    """Service for generating LLM responses with source citations"""
    
    def __init__(self):
        self.client = AsyncOpenAI(api_key=settings.openai_api_key)
    
    def _build_prompt(self, question: str, articles: List[Article]) -> str:
        """Build prompt with article context and user question
        
        Args:
            question: User's question
            articles: List of relevant articles
            
        Returns:
            Complete prompt string
        """
        if not articles:
            context = "No relevant articles found in the database."
        else:
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
            
            context = "\n".join(context_lines)
        
        prompt = f"""{context}

User Question: {question}

IMPORTANT INSTRUCTIONS:
1. Answer ONLY based on the provided articles
2. ALWAYS cite your sources using the format: "According to [Article N]..."
3. Include the source name and date when citing (e.g., "According to [Article 1] from CoinTelegraph (Jan 20, 2025)")
4. Use multiple citations if information comes from multiple articles
5. Be concise but thorough in your response
6. If the articles don't contain enough information to answer the question, clearly state that
7. At the end of your response, provide a "Sources:" section listing the article URLs you used

Now provide your answer:"""
        
        return prompt
    
    async def generate_streaming_response(
        self,
        question: str,
        articles: List[Article]
    ) -> AsyncGenerator[str, None]:
        """Generate streaming LLM response with citations
        
        Args:
            question: User's question
            articles: List of relevant articles
            
        Yields:
            Text chunks of the response
        """
        try:
            # Handle no articles case
            if not articles:
                yield "I apologize, but I couldn't find relevant articles in our database to answer this question. "
                yield "Please try a different query or try the web search feature for live internet search."
                return
            
            # Build prompt
            prompt = self._build_prompt(question, articles)
            
            # Call OpenAI API with streaming
            stream = await self.client.chat.completions.create(
                model="gpt-4o-mini",  # Using gpt-4o-mini for cost efficiency
                messages=[
                    {
                        "role": "system",
                        "content": "You are a crypto news analyst. You MUST cite your sources using the [Article N] format. Always include publication dates and source names in your citations."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                stream=True,
                temperature=0.5,  # Lower temperature for more factual responses
                max_tokens=800
            )
            
            # Yield chunks as they arrive
            chunk_count = 0
            async for chunk in stream:
                if chunk.choices[0].delta.content:
                    chunk_count += 1
                    content = chunk.choices[0].delta.content
                    logger.debug(f"Chunk {chunk_count}: {len(content)} chars")
                    yield content
            
            logger.info(f"LLM streaming complete: {chunk_count} chunks received from OpenAI")
        
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
