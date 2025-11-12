import logging
from fastapi import APIRouter, Depends
from datetime import datetime
from app.services.llm import get_llm_service, LLMService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["health"])

# Dependency function for FastAPI Depends()
def get_llm_service_dep() -> LLMService:
    """Dependency to get LLM service"""
    return get_llm_service()


@router.get("/health")
async def health_check(llm_service: LLMService = Depends(get_llm_service_dep)):
    """Health check endpoint with LLM provider info"""
    provider_info = llm_service.get_provider_info()
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "llm_provider": provider_info
    }

