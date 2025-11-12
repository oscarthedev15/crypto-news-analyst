import logging
import json
from typing import AsyncGenerator
from fastapi import APIRouter, Depends, HTTPException, Query, Header
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import Optional
from langchain_core.messages import HumanMessage, AIMessage

from app.database import get_db
from app.schemas import QuestionRequest
from app.services.moderation import get_moderation_service, ModerationService
from app.services.session import get_session_manager, SessionManager
from app.services.rag_agent import get_rag_agent_service, RAGAgentService
from app.services.llm import get_llm_service, LLMService
from app.services.search import get_search_service, SearchService

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


async def stream_rag_response(
    question: str,
    db: Session,
    session_manager: SessionManager,
    rag_agent_service: RAGAgentService,
    session_id: Optional[str] = None,
    top_k: int = 8
) -> AsyncGenerator[str, None]:
    """Stream RAG response in SSE format

    This generator:
    1. Retrieves chat history (if session_id provided)
    2. Gets article sources from semantic search
    3. Streams LLM response chunks in SSE format
    4. Saves conversation to session (if session_id provided)

    Args:
        question: User's question
        db: Database session
        session_manager: Session manager for chat history
        rag_agent_service: RAG agent service
        session_id: Optional session ID for conversation history
        top_k: Number of articles to retrieve

    Yields:
        SSE formatted strings (e.g., "data: {...}\\n\\n")
    """
    try:
        # Step 1: Get chat history for this session
        chat_history = None
        if session_id:
            chat_history = session_manager.get_messages(session_id)
            user_msgs = len([m for m in chat_history if isinstance(m, HumanMessage)])
            assistant_msgs = len([m for m in chat_history if isinstance(m, AIMessage)])
            logger.info(
                f"Session {session_id}: Retrieved {len(chat_history)} messages "
                f"({user_msgs} user + {assistant_msgs} assistant)"
            )
        else:
            logger.debug("No session_id provided, using stateless mode")

        # Step 2: Get article sources (single search call)
        articles_data = rag_agent_service.get_search_results_for_sources(
            question, db, chat_history, top_k
        )

        # Send sources as first SSE event
        sources_event = f"data: {json.dumps({'sources': articles_data})}\n\n"
        logger.info(f"Sending {len(articles_data)} article sources")
        yield sources_event

        # Step 3: Stream LLM response
        chunk_count = 0
        full_response = "" if session_id else None  # Only accumulate if we need to save

        async for chunk in rag_agent_service.generate_streaming_response(
            question, db, chat_history, top_k
        ):
            if chunk:
                chunk_count += 1

                # Accumulate only if we need to save to session
                if full_response is not None:
                    full_response += chunk

                # Send chunk as SSE event
                event = f"data: {json.dumps({'content': chunk})}\n\n"
                yield event

        logger.info(f"Streamed {chunk_count} chunks from LLM")

        # Step 4: Save conversation to session (if session_id provided)
        if session_id and full_response:
            session_manager.add_message(session_id, "user", question)
            session_manager.add_message(session_id, "assistant", full_response)
            logger.info(
                f"Session {session_id}: Saved conversation "
                f"(user: {len(question)} chars, assistant: {len(full_response)} chars)"
            )

        # Send completion signal
        yield f"data: {json.dumps({'done': True})}\n\n"

    except Exception as e:
        logger.error(f"Error streaming response: {e}", exc_info=True)
        yield f"data: {json.dumps({'error': str(e)})}\n\n"


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
    """Ask a question and get a streaming response with relevant article sources

    This endpoint:
    - Performs content moderation on the question
    - Retrieves relevant crypto news articles via semantic search
    - Generates a streaming response using RAG (Retrieval-Augmented Generation)
    - Maintains conversation history (if X-Session-Id header is provided)

    Args:
        request: Question request containing the user's question
        db: Database session (injected)
        moderation_service: Content moderation service (injected)
        session_manager: Session manager for chat history (injected)
        rag_agent_service: RAG agent service (injected)
        x_session_id: Optional session ID from header for conversation continuity
        top_k: Number of articles to retrieve (1-20, default: 8)

    Returns:
        StreamingResponse: SSE stream with article sources and LLM response

    Raises:
        HTTPException: 400 if question fails moderation check
    """
    # Run moderation check
    is_safe, reason = moderation_service.is_safe(request.question)
    if not is_safe:
        logger.warning(f"Question failed moderation: {reason}")
        raise HTTPException(status_code=400, detail=reason)

    logger.info(
        f"Processing question: '{request.question[:100]}...' "
        f"(session: {x_session_id or 'none'}, top_k: {top_k})"
    )

    # Stream response in SSE format
    return StreamingResponse(
        stream_rag_response(
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
            "X-Accel-Buffering": "no",  # Disable proxy buffering (nginx)
        }
    )
