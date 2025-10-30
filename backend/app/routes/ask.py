import logging
import json
from fastapi import APIRouter, Depends, HTTPException, Query, Header
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from datetime import datetime
from typing import AsyncGenerator, Optional
from langchain_core.messages import HumanMessage, AIMessage
from app.database import get_db
from app.schemas import QuestionRequest, IndexStats
from app.services.moderation import get_moderation_service
from app.services.search import get_search_service
from app.services.llm import get_llm_service
from app.services.session import get_session_manager
from app.services.rag_agent import get_rag_agent_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["search"])

# Services
moderation_service = get_moderation_service()
search_service = get_search_service()
llm_service = get_llm_service()
session_manager = get_session_manager()
rag_agent_service = get_rag_agent_service()


async def generate_sse_response(
    question: str,
    db: Session,
    session_id: Optional[str] = None,
    top_k: int = 8
) -> AsyncGenerator[str, None]:
    """Generate SSE formatted response with streaming RAG agent
    
    The RAG agent intelligently decides whether to search based on the question.
    Only searches when new information is needed, not for conversation context.
    
    Args:
        question: User's question
        db: Database session
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


@router.post("/ask")
async def ask_question(
    request: QuestionRequest,
    db: Session = Depends(get_db),
    x_session_id: Optional[str] = Header(None, alias="X-Session-Id"),
    top_k: int = Query(8, ge=1, le=20, description="Number of articles to retrieve (1-20, default: 8)")
):
    """Handle user questions with RAG agent (intelligent search + streaming response)
    
    Args:
        request: Question request with user question
        db: Database session
        x_session_id: Optional session ID from header for chat history
        top_k: Number of articles to retrieve if search is performed (default: 8)
        
    Returns:
        StreamingResponse with SSE formatted chunks
    """
    # Run moderation check
    is_safe, reason = moderation_service.is_safe(request.question)
    if not is_safe:
        raise HTTPException(status_code=400, detail=reason)
    
    logger.info(f"Processing question: {request.question[:100]}... (session: {x_session_id or 'none'})")
    
    # Return streaming response
    return StreamingResponse(
        generate_sse_response(request.question, db, x_session_id, top_k),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable proxy buffering
        }
    )


@router.get("/health")
async def health_check():
    """Health check endpoint with LLM provider info"""
    provider_info = llm_service.get_provider_info()
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "llm_provider": provider_info
    }


@router.get("/index-stats")
async def get_index_stats(db: Session = Depends(get_db)):
    """Get statistics about the search index"""
    stats = search_service.get_index_stats(db)
    return IndexStats(**stats)


@router.post("/rebuild-index")
async def rebuild_index(db: Session = Depends(get_db)):
    """Manually rebuild Qdrant index (admin only)"""
    try:
        logger.info("Manually rebuilding search index...")
        search_service.build_index(db)
        
        stats = search_service.get_index_stats(db)
        return {
            "status": "success",
            "message": "Index rebuilt successfully",
            "article_count": stats["indexed_articles"]
        }
    except Exception as e:
        logger.error(f"Error rebuilding index: {e}")
        raise HTTPException(status_code=500, detail=f"Error rebuilding index: {str(e)}")


@router.get("/sources")
async def get_sources(db: Session = Depends(get_db)):
    """Get list of news sources with statistics"""
    stats = search_service.get_index_stats(db)
    
    sources_list = []
    for source, count in stats["articles_by_source"].items():
        sources_list.append({
            "name": source,
            "count": count,
            "url": {
                "CoinTelegraph": "https://cointelegraph.com",
                "TheDefiant": "https://thedefiant.io",
                "Decrypt": "https://decrypt.co"
            }.get(source, "")
        })
    
    return {
        "sources": sources_list,
        "total_articles": stats["total_articles"],
        "last_refresh": stats["last_refresh"]
    }


@router.delete("/session/{session_id}")
async def clear_session(session_id: str):
    """Clear a specific chat session
    
    Args:
        session_id: Session ID to clear
        
    Returns:
        Success message
    """
    session_manager.clear_session(session_id)
    logger.info(f"Cleared session: {session_id}")
    return {
        "status": "success",
        "message": f"Session {session_id} cleared",
        "session_id": session_id
    }


@router.get("/sessions/stats")
async def get_session_stats():
    """Get statistics about active sessions (admin/debug endpoint)
    
    Returns:
        Session statistics including active sessions and message counts
    """
    stats = session_manager.get_session_stats()
    return stats
