import logging
import json
import re
from fastapi import APIRouter, Depends, HTTPException, Query, Header
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from typing import AsyncGenerator, Optional
from app.database import get_db
from app.schemas import QuestionRequest, IndexStats
from app.services.moderation import get_moderation_service
from app.services.search import get_search_service
from app.services.llm import get_llm_service
from app.services.session import get_session_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["search"])

# Services
moderation_service = get_moderation_service()
search_service = get_search_service()
llm_service = get_llm_service()
session_manager = get_session_manager()


async def generate_sse_response(
    question: str,
    db: Session,
    session_id: Optional[str] = None,
    recent_only: bool = True,
    top_k: int = 5,
    keyword_boost: float = 0.3
) -> AsyncGenerator[str, None]:
    """Generate SSE formatted response with streaming LLM chunks
    
    Args:
        question: User's question
        db: Database session
        session_id: Optional session ID for chat history
        recent_only: Filter to recent articles (last 30 days)
        top_k: Number of articles to retrieve
        keyword_boost: Weight for keyword matching (0.0-1.0, default 0.3)
        
    Yields:
        SSE formatted strings
    """
    try:
        # Calculate date filter
        date_filter = None
        if recent_only:
            date_filter = datetime.utcnow() - timedelta(days=30)
        
        # Semantic search for relevant articles
        search_results = search_service.search(
            question,
            db,
            top_k=top_k,
            date_filter=date_filter,
            keyword_boost=keyword_boost
        )
        
        # Extract articles and scores
        articles = [article for article, _ in search_results]
        
        # Send article metadata first
        articles_data = [
            {
                "id": article.id,
                "title": article.title,
                "source": article.source,
                "url": article.url,
                "published_date": article.published_date.isoformat() + "Z" if article.published_date else None,
                "similarity_score": next((score for art, score in search_results if art.id == article.id), 0.0)
            }
            for article in articles
        ]
        
        sources_event = f"data: {json.dumps({'sources': articles_data})}\n\n"
        logger.info(f"Sending sources event: {len(articles_data)} sources")
        yield sources_event
        
        # Get chat history for this session (if session_id provided)
        chat_history = None
        if session_id:
            chat_history = session_manager.get_messages(session_id)
            logger.info(f"Session {session_id}: Retrieved {len(chat_history)} messages from history")
        
        # Generate and stream LLM response
        chunk_count = 0
        full_response = ""
        async for chunk in llm_service.generate_streaming_response(question, articles, chat_history):
            if chunk:
                chunk_count += 1
                full_response += chunk
                # Escape JSON special characters and send as SSE
                event = f"data: {json.dumps({'content': chunk})}\n\n"
                yield event
        
        logger.info(f"Streamed {chunk_count} chunks")
        
        # Check if response uses article citations
        # Only hide sources if there are no citations AND the response explicitly says it doesn't have information from articles
        has_citations = bool(re.search(r'\[Article\s+\d+\]', full_response, re.IGNORECASE))
        response_lower = full_response.lower().strip()
        
        # Only hide sources if:
        # 1. No citations found AND
        # 2. Response explicitly mentions not having information from articles/recent news
        # (but NOT for casual greetings or general responses)
        explicit_no_info_patterns = [
            "i don't have information about that in the recent news articles",
            "i don't have recent articles about",
            "couldn't find relevant articles in our database"
        ]
        
        has_explicit_no_info = any(
            pattern in response_lower 
            for pattern in explicit_no_info_patterns
        )
        
        if has_explicit_no_info and not has_citations:
            # Send flag to hide sources only when explicitly saying no article info
            hide_sources_event = f"data: {json.dumps({'hideSources': True})}\n\n"
            logger.info("Detected explicit no-article-info response, hiding sources")
            yield hide_sources_event
        
        # Save conversation to session history
        if session_id and full_response:
            session_manager.add_message(session_id, "user", question)
            session_manager.add_message(session_id, "assistant", full_response)
            logger.info(f"Session {session_id}: Saved conversation (user + assistant messages)")
        
        # Send completion signal
        yield "data: [DONE]\n\n"
    
    except Exception as e:
        logger.error(f"Error in SSE response: {e}")
        yield f"data: {json.dumps({'error': str(e)})}\n\n"


@router.post("/ask")
async def ask_question(
    request: QuestionRequest,
    db: Session = Depends(get_db),
    x_session_id: Optional[str] = Header(None),
    recent_only: bool = Query(True, description="Filter to articles from last 30 days"),
    top_k: int = Query(5, ge=1, le=20, description="Number of articles to retrieve (1-20)"),
    keyword_boost: float = Query(0.3, ge=0.0, le=1.0, description="Deprecated: kept for API compatibility, not used in semantic-only search")
):
    """Handle user questions with semantic search and streaming LLM response
    
    Args:
        request: Question request with user question
        db: Database session
        x_session_id: Optional session ID from header for chat history
        recent_only: Filter to recent articles (default: True, last 30 days)
        top_k: Number of articles to retrieve (default: 5)
        keyword_boost: Weight for keyword matching (0.0-1.0, default: 0.3)
        
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
        generate_sse_response(request.question, db, x_session_id, recent_only, top_k, keyword_boost),
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
