import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.schemas import IndexStats
from app.services.index import get_index_service, IndexService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["index"])


@router.get("/index-stats")
async def get_index_stats(
    db: Session = Depends(get_db),
    index_service: IndexService = Depends(get_index_service)
):
    """Get statistics about the search index"""
    stats = index_service.get_index_stats(db)
    return IndexStats(**stats)


@router.post("/rebuild-index")
async def rebuild_index(
    db: Session = Depends(get_db),
    index_service: IndexService = Depends(get_index_service)
):
    """Manually rebuild Qdrant index (admin only)"""
    try:
        logger.info("Manually rebuilding search index...")
        index_service.build_index(db, recreate=True)

        stats = index_service.get_index_stats(db)
        return {
            "status": "success",
            "message": "Index rebuilt successfully",
            "article_count": stats["indexed_articles"]
        }
    except Exception as e:
        logger.error(f"Error rebuilding index: {e}")
        raise HTTPException(status_code=500, detail=f"Error rebuilding index: {str(e)}")

