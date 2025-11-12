import logging
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.services.search import get_search_service, SearchService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["sources"])

# Dependency function for FastAPI Depends()
def get_search_service_dep() -> SearchService:
    """Dependency to get search service"""
    return get_search_service()


@router.get("/sources")
async def get_sources(
    db: Session = Depends(get_db),
    search_service: SearchService = Depends(get_search_service_dep)
):
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
                "DLNews": "https://www.dlnews.com"
            }.get(source, "")
        })
    
    return {
        "sources": sources_list,
        "total_articles": stats["total_articles"],
        "last_refresh": stats["last_refresh"]
    }

