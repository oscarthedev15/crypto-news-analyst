import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.database import init_db
from app.services.search import get_search_service
from app.routes import ask

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title=settings.app_title,
    description=settings.app_description,
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(ask.router)


@app.on_event("startup")
async def startup_event():
    """Initialize database and load search index on startup"""
    logger.info("Starting up application...")
    
    # Initialize database
    init_db()
    logger.info("Database initialized")
    
    # Load or build FAISS index
    search_service = get_search_service()
    if not search_service.load_index():
        logger.warning("Search index not found. Please run: python scripts/ingest_news.py")
        logger.info("Application started without search index. Data ingestion required.")
    else:
        logger.info("Search index loaded successfully")


@app.get("/")
async def root():
    """Root endpoint with welcome message"""
    return {
        "title": settings.app_title,
        "description": settings.app_description,
        "version": "1.0.0",
        "docs": "/docs",
        "message": "Welcome to the Crypto News Agent API",
        "endpoints": {
            "ask": "POST /api/ask - Semantic search over local news articles",
            "health": "GET /api/health - Health check",
            "index_stats": "GET /api/index-stats - Database statistics",
            "sources": "GET /api/sources - News sources information"
        }
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )
