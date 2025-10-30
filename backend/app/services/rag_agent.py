import logging
from typing import List, Optional, AsyncGenerator, Dict
from sqlalchemy.orm import Session
from langchain_core.messages import HumanMessage, SystemMessage, BaseMessage
from langchain_core.documents import Document

from app.services.search import get_search_service
from app.services.llm import get_llm_service

logger = logging.getLogger(__name__)


class RAGAgentService:
    """RAG Agent service that uses tools for semantic search and query improvement"""
    
    def __init__(self):
        self.search_service = get_search_service()
        self.llm_service = get_llm_service()
    
    def _perform_search(self, query: str, db: Session, top_k: int = 8) -> tuple[str, List[Document]]:
        """Perform semantic search and return formatted results"""
        try:
            # Limit top_k to reasonable range (allow up to 20 for better multi-source synthesis)
            top_k = min(max(1, top_k), 20)
            
            # Perform semantic search
            search_results = self.search_service.search(query, db, top_k=top_k)
            
            if not search_results:
                return "No relevant articles found.", []
            
            # Build serialized content and document artifacts
            serialized_parts = []
            documents = []
            
            for i, (article, score) in enumerate(search_results, 1):
                date_str = article.published_date.strftime("%b %d, %Y") if article.published_date else "Unknown"
                
                # Serialized format for LLM
                serialized_parts.append(
                    f"[Article {i}]\n"
                    f"Title: {article.title}\n"
                    f"Source: {article.source} ({date_str})\n"
                    f"URL: {article.url}\n"
                    f"Content: {article.content[:500] if article.content else 'No content'}...\n"
                    f"Relevance Score: {score:.2f}"
                )
                
                # Document artifact for metadata access
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
            
            serialized = "\n\n".join(serialized_parts)
            logger.info(f"Semantic search: Found {len(documents)} articles for query: {query[:50]}")
            
            return serialized, documents
            
        except Exception as e:
            logger.error(f"Error in semantic search: {e}")
            return f"Error searching: {str(e)}", []
    
    def _improve_query(self, original_query: str) -> str:
        """Improve a search query for better semantic search results"""
        try:
            # Simple heuristic-based improvement
            improved = original_query.strip()
            
            # Expand common abbreviations
            abbreviations = {
                "btc": "Bitcoin",
                "eth": "Ethereum",
                "crypto": "cryptocurrency",
            }
            
            for abbr, full in abbreviations.items():
                if abbr.lower() in improved.lower():
                    improved = improved.replace(abbr, full)
            
            logger.debug(f"Query improvement: '{original_query}' -> '{improved}'")
            return improved
            
        except Exception as e:
            logger.error(f"Error improving query: {e}")
            return original_query
    
    def _build_system_prompt(self) -> str:
        """Build system prompt for the RAG agent"""
        return """You are a crypto news analyst assistant that provides information EXCLUSIVELY from recent news articles in the database.

CRITICAL PRIORITY: ARTICLES FIRST, GENERAL KNOWLEDGE LAST

1. ARTICLE INFORMATION IS PRIMARY:
   - When articles are provided, you MUST prioritize and focus on information from those articles
   - Start your response with specific details from the articles
   - Base your entire answer on article content - use it as the foundation
   - Only add minimal general context if absolutely necessary to frame the article information
   - NEVER lead with general knowledge when articles are available
   - Example: If articles mention "Bitcoin ETFs saw $470M outflows", lead with that specific fact, not general Bitcoin explanation

2. USING ARTICLES EFFECTIVELY - MULTI-SOURCE SYNTHESIS REQUIRED:
   - When multiple articles are provided, you MUST synthesize information from MULTIPLE sources
   - IDEALLY use at least 2-3 different articles/sources in your response when available
   - Extract specific facts, numbers, dates, and details from articles
   - Cite EVERY fact from articles using format: "[Article N] from [Source] (Date: <DATE_STRING>)"
   - Use the EXACT date string provided with each article (e.g., "Oct 29, 2025").
   - Never write placeholders like "[Date]"; if no date is available, use "Unknown".
   - Quote specific details: prices, amounts, company names, dates, events
   - If multiple articles cover the topic, actively reference information from multiple articles
   - Compare and contrast different perspectives or details from different sources when relevant
   - Structure your response around the article content, not general knowledge
   - AVOID responses that only cite a single article when multiple articles are available

3. GENERAL KNOWLEDGE RESTRICTIONS:
   - DO NOT provide extensive general knowledge explanations when articles are available
   - If articles are provided, general knowledge should be MINIMAL (1-2 sentences max, only for context)
   - General knowledge should NEVER overshadow article information
   - Only use general knowledge if articles don't cover basic context needed to understand the article content
   - Example: Don't explain "Bitcoin is a cryptocurrency..." if articles already cover the topic - jump straight to article details

4. CHAT HISTORY AWARENESS:
   - You have access to ALL previous messages in this conversation (they appear BEFORE the current user message)
   - When the user asks about something mentioned earlier (e.g., "that article", "what you said", "what question did I just ask"), ALWAYS check the chat history first
   - DO NOT use the search tool for questions about the conversation itself - use chat history instead
   - Examples where you should NOT search:
     * "what question did i just ask?" -> Check chat history for the previous HumanMessage
     * "tell me more about that" -> Check chat history for what was discussed
     * "what did you say about bitcoin?" -> Check chat history for previous AI messages

5. RESPONSE STRUCTURE WHEN ARTICLES ARE PROVIDED:
   - Start: Specific fact/event from articles (with citation)
   - Middle: Additional details from articles (with citations)
   - End: Minimal general context ONLY if needed (1 sentence max)
   - Format: Lead with article facts, support with article details, minimal general context at end

6. RESPONSE STRUCTURE WHEN NO ARTICLES:
   - If search returns no results AND chat history doesn't help, then you may use general knowledge
   - But always mention that no recent articles were found
   - Example: "I couldn't find recent articles about this topic, but generally..."

7. GREETINGS AND SMALL TALK:
   - Do NOT use search tool for greetings, casual conversation, or "how are you" type questions
   - Respond naturally without searching

REMEMBER: Your primary job is to share information from the articles. Articles are your source of truth. General knowledge is a last resort, not the primary answer."""
    
    async def generate_streaming_response(
        self,
        question: str,
        db: Session,
        chat_history: Optional[List[BaseMessage]] = None,
        top_k: int = 8
    ) -> AsyncGenerator[str, None]:
        """Generate streaming response using RAG agent with intelligent search
        
        The agent decides whether to search based on the question and chat history.
        Only searches when new information is needed, not for conversation context.
        
        Args:
            question: User's question
            db: Database session
            chat_history: Optional list of previous messages
            top_k: Default number of articles to retrieve
            
        Yields:
            Text chunks of the response
        """
        try:
            # Determine if we should search
            should_search = self.should_search(question, chat_history)
            
            # Build messages list
            messages = [SystemMessage(content=self._build_system_prompt())]
            
            # Add chat history if provided
            if chat_history:
                messages.extend(chat_history)
                logger.info(f"RAG Agent: Added {len(chat_history)} messages from chat history")
            
            # If we should search, improve query and perform search
            if should_search:
                # Improve the query for better search results
                improved_query = self._improve_query(question)
                
                # Perform semantic search
                search_results_text, search_documents = self._perform_search(improved_query, db, top_k=top_k)
                
                # Build context message
                if search_documents:
                    num_articles = len(search_documents)
                    multi_source_instruction = ""
                    if num_articles > 1:
                        multi_source_instruction = f"""
- MULTI-SOURCE SYNTHESIS REQUIRED: You have {num_articles} articles available. USE MULTIPLE SOURCES in your answer.
- Ideally reference information from at least 2-3 different articles when answering
- Synthesize information across multiple articles to provide a comprehensive answer
- Compare or combine details from different sources when relevant
- DO NOT limit your answer to just one article when multiple are available"""
                    
                    context_message = f"""CRITICAL: Answer the user's question using PRIMARILY information from these articles. These articles are your PRIMARY source of information.

Here are relevant crypto news articles retrieved from the database (top-k retrieval):

{search_results_text}

INSTRUCTIONS:
- Base your entire response on these articles
- Start with specific facts, numbers, and details from the articles{multi_source_instruction}
- Cite EVERY fact using format: "[Article N] from [Source] (Date: <DATE_STRING>)"
- Use the EXACT date string shown above for each article (e.g., "Oct 29, 2025"). Never write placeholders like "[Date]".
- Only add minimal general context (1-2 sentences max) if absolutely needed for basic understanding
- DO NOT lead with general knowledge - lead with article information
- Extract and highlight specific details: prices, amounts, dates, events, company names from the articles
- When multiple articles are available, actively use information from multiple sources

Remember: Articles are PRIMARY, general knowledge is SECONDARY and MINIMAL. When multiple articles are provided, synthesize across them."""
                    
                    # Add context as a system message
                    messages.append(SystemMessage(content=context_message))
                    logger.info(f"RAG Agent: Performed search, found {len(search_documents)} articles")
                else:
                    logger.info("RAG Agent: Search returned no results")
            else:
                logger.info("RAG Agent: Skipping search (using chat history only)")
            
            # Add current question
            messages.append(HumanMessage(content=question))
            
            # Stream response from LLM
            async for chunk in self.llm_service.langchain_llm.astream(messages):
                if chunk.content:
                    yield chunk.content
        
        except Exception as e:
            logger.error(f"Error in RAG agent: {e}")
            yield f"Error generating response: {str(e)}"
    
    def get_search_results_for_sources(
        self,
        question: str,
        db: Session,
        chat_history: Optional[List[BaseMessage]] = None,
        top_k: int = 8
    ) -> List[Dict]:
        """Get search results formatted for frontend sources display
        
        This is called separately to get sources metadata without duplicating search.
        Only performs search if should_search returns True.
        
        Returns:
            List of article dictionaries for frontend display
        """
        if not self.should_search(question, chat_history):
            return []
        
        try:
            improved_query = self._improve_query(question)
            search_results = self.search_service.search(improved_query, db, top_k=top_k)
            
            # Extract articles and scores, deduplicating by article ID
            seen_ids = set()
            articles_data = []
            
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
            
            return articles_data
        except Exception as e:
            logger.error(f"Error getting search results for sources: {e}")
            return []
    
    def should_search(self, question: str, chat_history: Optional[List[BaseMessage]] = None) -> bool:
        """Heuristic to determine if we should search (fallback when tool calling not available)"""
        question_lower = question.lower().strip()
        
        # Don't search for conversation meta-questions
        conversation_keywords = [
            "what question did i",
            "what did i ask",
            "what did you say",
            "tell me more about that",
            "that article",
            "you mentioned",
            "you said"
        ]
        
        if any(keyword in question_lower for keyword in conversation_keywords):
            return False
        
        # Don't search for greetings
        greetings = ["hello", "hi", "hey", "how are you", "good morning", "good afternoon", "good evening"]
        if any(question_lower.startswith(greeting) for greeting in greetings):
            return False
        
        # Search for actual information queries
        return True


# Singleton instance
_rag_agent_service = None

def get_rag_agent_service() -> RAGAgentService:
    """Get or create the RAG agent service singleton"""
    global _rag_agent_service
    if _rag_agent_service is None:
        _rag_agent_service = RAGAgentService()
    return _rag_agent_service

