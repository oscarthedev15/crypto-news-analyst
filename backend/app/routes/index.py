import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.schemas import IndexStats
from app.services.search import get_search_service, SearchService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["index"])

# Dependency function for FastAPI Depends()
def get_search_service_dep() -> SearchService:
    """Dependency to get search service"""
    return get_search_service()


@router.get("/index-stats")
async def get_index_stats(
    db: Session = Depends(get_db),
    search_service: SearchService = Depends(get_search_service_dep)
):
    """Get statistics about the search index"""
    stats = search_service.get_index_stats(db)
    return IndexStats(**stats)


@router.post("/rebuild-index")
async def rebuild_index(
    db: Session = Depends(get_db),
    search_service: SearchService = Depends(get_search_service_dep)
):
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

