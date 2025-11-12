import logging
from typing import List, Optional, AsyncGenerator, Dict
from sqlalchemy.orm import Session
from langchain_core.messages import HumanMessage, SystemMessage, BaseMessage
from langchain_core.documents import Document

from app.services.search import SearchService, get_search_service
from app.services.llm import LLMService, get_llm_service

logger = logging.getLogger(__name__)


class RAGAgentService:
    """RAG service focused on semantic search and article-based responses

    Uses traditional RAG pattern:
    1. Perform semantic search for the query
    2. Format retrieved articles as context
    3. Generate LLM response with context
    """

    def __init__(self, search_service: SearchService, llm_service: LLMService):
        self.search_service = search_service
        self.llm_service = llm_service

    def _format_articles_context(self, search_results: List[tuple], top_k: int = 8) -> tuple[str, List[Document]]:
        """Format search results into context for the LLM

        Returns:
            Tuple of (formatted_context_string, list_of_documents)
        """
        if not search_results:
            return "", []

        documents = []
        formatted_parts = []

        for i, (article, score) in enumerate(search_results[:top_k], 1):
            date_str = article.published_date.strftime("%b %d, %Y") if article.published_date else "Unknown"

            # Create LangChain document for potential further use
            doc = Document(
                page_content=article.content or article.title,
                metadata={
                    "id": article.id,
                    "title": article.title,
                    "source": article.source,
                    "url": article.url,
                    "published_date": article.published_date.isoformat() + "Z" if article.published_date else None,
                    "similarity_score": float(score)
                }
            )
            documents.append(doc)

            # Format for LLM context
            content_preview = (article.content[:500] + "...") if article.content else "No content available"
            formatted_parts.append(
                f"[Article {i}]\n"
                f"Title: {article.title}\n"
                f"Source: {article.source} ({date_str})\n"
                f"URL: {article.url}\n"
                f"Content: {content_preview}"
            )

        context = "\n\n".join(formatted_parts)
        return context, documents

    def _build_contextual_query(self, question: str, chat_history: Optional[List[BaseMessage]] = None) -> str:
        """Build a search query that incorporates chat history context

        This helps with follow-up questions like:
        - User: "What happened with Bitcoin?"
        - User: "What about Ethereum?" -> reformulated to include Bitcoin context

        Args:
            question: Current user question
            chat_history: Previous conversation messages

        Returns:
            Enhanced search query string
        """
        if not chat_history or len(chat_history) == 0:
            return question

        # Extract recent context (last 2-3 turns for relevance)
        recent_messages = chat_history[-4:] if len(chat_history) > 4 else chat_history

        # Build context from recent exchanges
        context_parts = []
        for msg in recent_messages:
            if isinstance(msg, HumanMessage):
                context_parts.append(f"User asked: {msg.content}")
            elif isinstance(msg, BaseMessage) and hasattr(msg, 'content') and msg.content:
                # Capture assistant responses (truncated to avoid token bloat)
                content_preview = msg.content[:150] if len(msg.content) > 150 else msg.content
                context_parts.append(f"Context: {content_preview}")

        # Combine recent context with current question
        if context_parts:
            context_summary = " | ".join(context_parts[-3:])  # Last 3 most relevant
            contextual_query = f"{context_summary} | Current question: {question}"
            logger.debug(f"Reformulated query: {contextual_query[:100]}...")
            return contextual_query

        return question

    def _build_system_prompt(self, context: str = "") -> str:
        """Build system prompt with optional article context"""
        base_prompt = "You are a crypto news analyst assistant that helps users understand recent cryptocurrency news and market activity."

        if context:
            return f"""{base_prompt}

RELEVANT ARTICLES:
{context}

INSTRUCTIONS:
- Answer the question using information from the articles above
- Cite sources using format: "[Article N] from [Source] (Date: [DATE])"
- Synthesize information from multiple articles when available
- If the articles don't contain relevant information, acknowledge this and provide a brief general response"""

        return f"""{base_prompt}

No relevant articles were found for this query. You can provide a brief general response or suggest the user ask about recent news topics."""

    async def generate_streaming_response(
        self,
        question: str,
        db: Session,
        chat_history: Optional[List[BaseMessage]] = None,
        top_k: int = 8
    ) -> AsyncGenerator[str, None]:
        """Generate streaming response using RAG pattern with chat history awareness

        This hybrid approach:
        1. Uses chat history to create a better search query
        2. Performs semantic search with the contextualized query
        3. Includes full chat history in LLM context for coherent responses
        """
        try:
            # Step 1: Build contextual search query from chat history
            search_query = self._build_contextual_query(question, chat_history)
            logger.info(f"Performing semantic search for: {question[:50]}...")
            if search_query != question:
                logger.info(f"Enhanced with context: {search_query[:80]}...")

            # Step 2: Perform semantic search with contextualized query
            search_results = self.search_service.search(search_query, db, top_k=top_k)

            # Step 3: Format articles as context
            context, documents = self._format_articles_context(search_results, top_k)

            if documents:
                logger.info(f"Retrieved {len(documents)} relevant articles")
            else:
                logger.info("No relevant articles found")

            # Step 4: Build messages with article context
            messages = [SystemMessage(content=self._build_system_prompt(context))]

            # Step 5: Add full chat history for conversational coherence
            if chat_history:
                messages.extend(chat_history)
                logger.info(f"Added {len(chat_history)} messages from history")

            messages.append(HumanMessage(content=question))

            # Step 6: Stream LLM response
            async for chunk in self.llm_service.langchain_llm.astream(messages):
                if chunk.content:
                    yield chunk.content

        except Exception as e:
            logger.error(f"Error in RAG service: {e}", exc_info=True)
            yield f"Error generating response: {str(e)}"

    def get_search_results_for_sources(
        self,
        question: str,
        db: Session,
        chat_history: Optional[List[BaseMessage]] = None,
        top_k: int = 8
    ) -> List[Dict]:
        """Get article sources for a question (for citation/reference purposes)

        Uses the same contextual query logic to ensure consistency with response generation.
        """
        try:
            # Use contextual query for consistency
            search_query = self._build_contextual_query(question, chat_history)
            search_results = self.search_service.search(search_query, db, top_k=top_k)

            articles_data = []
            seen_ids = set()

            for article, score in search_results:
                if article.id not in seen_ids:
                    articles_data.append({
                        "id": article.id,
                        "title": article.title,
                        "source": article.source,
                        "url": article.url,
                        "published_date": article.published_date.isoformat() + "Z" if article.published_date else None,
                        "similarity_score": float(score)
                    })
                    seen_ids.add(article.id)

            logger.info(f"Found {len(articles_data)} source articles")
            return articles_data

        except Exception as e:
            logger.error(f"Error getting search results: {e}", exc_info=True)
            return []


_rag_agent_service = None

def get_rag_agent_service(
    search_service: Optional[SearchService] = None,
    llm_service: Optional[LLMService] = None
) -> RAGAgentService:
    global _rag_agent_service
    
    if search_service is not None or llm_service is not None:
        return RAGAgentService(
            search_service=search_service or get_search_service(),
            llm_service=llm_service or get_llm_service()
        )
    
    if _rag_agent_service is None:
        _rag_agent_service = RAGAgentService(
            search_service=get_search_service(),
            llm_service=get_llm_service()
        )
    return _rag_agent_service
