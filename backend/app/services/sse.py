import logging
import json
from typing import AsyncGenerator, Optional
from sqlalchemy.orm import Session
from langchain_core.messages import HumanMessage, AIMessage

from app.services.session import SessionManager
from app.services.rag_agent import RAGAgentService


logger = logging.getLogger(__name__)


async def generate_sse_response(
    question: str,
    db: Session,
    session_manager: SessionManager,
    rag_agent_service: RAGAgentService,
    session_id: Optional[str] = None,
    top_k: int = 8
) -> AsyncGenerator[str, None]:
    """Generate SSE formatted response with streaming RAG agent
    
    The RAG agent intelligently decides whether to search based on the question.
    Only searches when new information is needed, not for conversation context.
    
    Args:
        question: User's question
        db: Database session
        session_manager: Session manager for chat history (injected)
        rag_agent_service: RAG agent service for generating responses (injected)
        session_id: Optional session ID for chat history
        top_k: Number of articles to retrieve (if search is performed, default: 8)
        
    Yields:
        SSE formatted strings
    """
    try:
        # Get chat history for this session (if session_id provided)
        chat_history = None
        if session_id:
            chat_history = session_manager.get_messages(session_id)
            user_msgs = len([m for m in chat_history if isinstance(m, HumanMessage)])
            assistant_msgs = len([m for m in chat_history if isinstance(m, AIMessage)])
            logger.info(f"Session {session_id}: Retrieved {len(chat_history)} messages from history ({user_msgs} user + {assistant_msgs} assistant)")
            if chat_history:
                # Log recent messages for debugging
                recent_msgs = chat_history[-4:] if len(chat_history) > 4 else chat_history
                for i, msg in enumerate(recent_msgs):
                    msg_type = "Human" if isinstance(msg, HumanMessage) else "AI"
                    content_preview = msg.content[:80] if hasattr(msg, 'content') else str(msg)[:80]
                    logger.debug(f"  Recent[{i}]: {msg_type} - {content_preview}...")
        else:
            logger.debug("No session_id provided, no chat history will be used")
        
        # Get sources from RAG agent (only if search will be performed)
        articles_data = rag_agent_service.get_search_results_for_sources(
            question, db, chat_history, top_k
        )
        
        # Send article metadata
        sources_event = f"data: {json.dumps({'sources': articles_data})}\n\n"
        logger.info(f"Sending sources event: {len(articles_data)} sources")
        yield sources_event
        
        # Generate and stream RAG agent response
        chunk_count = 0
        full_response = ""
        async for chunk in rag_agent_service.generate_streaming_response(
            question, db, chat_history, top_k
        ):
            if chunk:
                chunk_count += 1
                full_response += chunk
                # Escape JSON special characters and send as SSE
                event = f"data: {json.dumps({'content': chunk})}\n\n"
                yield event
        
        logger.info(f"Streamed {chunk_count} chunks via RAG agent")
        
        # Save conversation to session history
        if session_id and full_response:
            session_manager.add_message(session_id, "user", question)
            session_manager.add_message(session_id, "assistant", full_response)
            logger.info(f"Session {session_id}: Saved conversation (user: '{question[:50]}...', assistant: {len(full_response)} chars)")
            
            # Verify the save worked
            verify_history = session_manager.get_messages(session_id)
            logger.debug(f"Session {session_id}: Verification - now has {len(verify_history)} messages in history")
        
        # Send completion signal
        yield "data: [DONE]\n\n"
    
    except Exception as e:
        logger.error(f"Error in SSE response: {e}")
        yield f"data: {json.dumps({'error': str(e)})}\n\n"


