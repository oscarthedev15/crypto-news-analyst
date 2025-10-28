import logging
import json
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from datetime import datetime
from typing import AsyncGenerator
from openai import AsyncOpenAI
from app.schemas import QuestionRequest
from app.services.moderation import get_moderation_service
from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["web-search"])

moderation_service = get_moderation_service()


async def generate_websearch_response(question: str) -> AsyncGenerator[str, None]:
    """Generate web search response using OpenAI
    
    Args:
        question: User's question
        
    Yields:
        SSE formatted strings
    """
    try:
        client = AsyncOpenAI(api_key=settings.openai_api_key)
        
        # Use OpenAI with web search capabilities
        stream = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": """You are a crypto news analyst with access to the web. 
                    Search the web for recent cryptocurrency news to answer the user's question. 
                    Cite specific URLs and publication dates in your response.
                    Format citations as: 'According to [URL] (Source Name, Date)...'
                    At the end, provide a Sources section with URLs."""
                },
                {
                    "role": "user",
                    "content": f"Search for and summarize recent crypto news about: {question}"
                }
            ],
            stream=True,
            temperature=0.5,
            max_tokens=800
        )
        
        # Send metadata about web search
        yield f"data: {json.dumps({'mode': 'web-search', 'timestamp': datetime.utcnow().isoformat() + 'Z'})}\n\n"
        
        # Stream response chunks
        async for chunk in stream:
            if chunk.choices[0].delta.content:
                content = chunk.choices[0].delta.content
                yield f"data: {json.dumps({'content': content})}\n\n"
        
        yield "data: [DONE]\n\n"
    
    except Exception as e:
        logger.error(f"Error in web search: {e}")
        yield f"data: {json.dumps({'error': str(e)})}\n\n"


@router.post("/ask-websearch")
async def ask_websearch(request: QuestionRequest):
    """Handle user questions with web search via OpenAI
    
    Args:
        request: Question request with user question
        
    Returns:
        StreamingResponse with SSE formatted chunks
    """
    # Run moderation check
    is_safe, reason = moderation_service.is_safe(request.question)
    if not is_safe:
        raise HTTPException(status_code=400, detail=reason)
    
    logger.info(f"Processing web search question: {request.question[:100]}...")
    
    # Return streaming response
    return StreamingResponse(
        generate_websearch_response(request.question),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )
