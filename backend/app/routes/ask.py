import logging
from fastapi import APIRouter, Depends, HTTPException, Query, Header
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import Optional
from app.database import get_db
from app.schemas import QuestionRequest
from app.services.moderation import get_moderation_service, ModerationService
from app.services.session import get_session_manager, SessionManager
from app.services.rag_agent import get_rag_agent_service, RAGAgentService
from app.services.llm import get_llm_service, LLMService
from app.services.search import get_search_service, SearchService
from app.services.sse import generate_sse_response

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["ask"])


def get_rag_agent_service_dep(
    search_service: SearchService = Depends(get_search_service),
    llm_service: LLMService = Depends(get_llm_service)
) -> RAGAgentService:
    """FastAPI dependency to get RAG agent service with injected dependencies"""
    return get_rag_agent_service(
        search_service=search_service,
        llm_service=llm_service
    )


@router.post("/ask")
async def ask_question(
    request: QuestionRequest,
    db: Session = Depends(get_db),
    moderation_service: ModerationService = Depends(get_moderation_service),
    session_manager: SessionManager = Depends(get_session_manager),
    rag_agent_service: RAGAgentService = Depends(get_rag_agent_service_dep),
    x_session_id: Optional[str] = Header(None, alias="X-Session-Id"),
    top_k: int = Query(8, ge=1, le=20, description="Number of articles to retrieve (1-20, default: 8)")
):
    """Handle user questions with RAG agent (intelligent search + streaming response)
    
    Args:
        request: Question request with user question
        db: Database session
        moderation_service: Moderation service (injected)
        session_manager: Session manager (injected)
        rag_agent_service: RAG agent service (injected)
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
        generate_sse_response(
            request.question, 
            db, 
            session_manager, 
            rag_agent_service, 
            x_session_id, 
            top_k
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable proxy buffering
        }
    )
