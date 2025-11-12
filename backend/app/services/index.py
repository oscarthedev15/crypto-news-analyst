import logging
from typing import Optional, Dict
from datetime import datetime
from sqlalchemy.orm import Session

from langchain_qdrant import QdrantVectorStore, RetrievalMode, FastEmbedSparse
from langchain_core.documents import Document
from qdrant_client import QdrantClient

from app.models import Article
from app.services.embeddings import EmbeddingService
from app.config import settings

logger = logging.getLogger(__name__)

COLLECTION_NAME = "crypto_news_articles"


class IndexService:
    """Service for building and managing vector search indexes

    Responsibilities:
    - Building indexes from database articles
    - Managing Qdrant collections (create, delete, check)
    - Providing index statistics

    Used by: Ingestion scripts, rebuild endpoints
    """

    def __init__(self, embedding_service: EmbeddingService):
        self.embedding_service = embedding_service
        self.qdrant_client = None
        self.sparse_embeddings = None

        # Initialize Qdrant client
        try:
            client_kwargs = {"url": settings.qdrant_url}
            if settings.qdrant_api_key:
                client_kwargs["api_key"] = settings.qdrant_api_key
            self.qdrant_client = QdrantClient(**client_kwargs)
            logger.info(f"Initialized Qdrant client: {settings.qdrant_url}")
        except Exception as e:
            logger.error(f"Failed to initialize Qdrant client: {e}")
            raise

        # Initialize sparse embeddings for hybrid search
        try:
            self.sparse_embeddings = FastEmbedSparse(model_name="Qdrant/bm25")
            logger.info("Initialized sparse embeddings for hybrid search")
        except Exception as e:
            logger.error(f"Failed to initialize sparse embeddings: {e}")
            # Don't raise - allow dense-only mode

    def collection_exists(self) -> bool:
        """Check if the collection exists in Qdrant"""
        try:
            collections = self.qdrant_client.get_collections().collections
            return any(c.name == COLLECTION_NAME for c in collections)
        except Exception as e:
            logger.error(f"Error checking collection existence: {e}")
            return False

    def get_collection_point_count(self) -> Optional[int]:
        """Get the number of documents in the collection"""
        try:
            if not self.collection_exists():
                return 0
            collection_info = self.qdrant_client.get_collection(COLLECTION_NAME)
            return collection_info.points_count if collection_info else 0
        except Exception as e:
            logger.error(f"Error getting collection point count: {e}")
            return None

    def delete_collection(self):
        """Delete the existing collection"""
        try:
            if self.collection_exists():
                logger.info(f"Deleting collection '{COLLECTION_NAME}'")
                self.qdrant_client.delete_collection(COLLECTION_NAME)
                logger.info("Collection deleted successfully")
        except Exception as e:
            logger.error(f"Error deleting collection: {e}")
            raise

    def build_index(self, db: Session, recreate: bool = True):
        """Build vector search index from database articles

        Args:
            db: Database session
            recreate: If True, delete existing collection before building

        Raises:
            RuntimeError: If sparse embeddings are unavailable (hybrid search required)
        """
        logger.info("Building vector search index with hybrid search...")

        # Require sparse embeddings for hybrid search
        if not self.sparse_embeddings:
            raise RuntimeError(
                "Cannot build index: Sparse embeddings not available. "
                "Hybrid search is required. Install: pip install fastembed>=0.2.0"
            )

        # Fetch all articles
        articles = db.query(Article).all()
        if not articles:
            logger.warning("No articles found to index")
            return

        logger.info(f"Indexing {len(articles)} articles...")

        # Convert to LangChain documents
        documents = []
        for article in articles:
            doc = Document(
                page_content=f"{article.title} {article.content}",
                metadata={
                    "id": article.id,
                    "title": article.title,
                    "source": article.source,
                    "url": article.url,
                    "published_date": article.published_date.isoformat() + "Z" if article.published_date else None,
                }
            )
            documents.append(doc)

        # Delete existing collection if requested
        if recreate:
            self.delete_collection()

        # Build vector store with hybrid search
        logger.info("Creating Qdrant vector store with hybrid search (dense + sparse)...")
        vectorstore_kwargs = {
            "documents": documents,
            "embedding": self.embedding_service.langchain_embeddings,
            "sparse_embedding": self.sparse_embeddings,
            "url": settings.qdrant_url,
            "collection_name": COLLECTION_NAME,
            "retrieval_mode": RetrievalMode.HYBRID,
            "vector_name": "dense",
            "sparse_vector_name": "sparse",
        }
        if settings.qdrant_api_key:
            vectorstore_kwargs["api_key"] = settings.qdrant_api_key

        QdrantVectorStore.from_documents(**vectorstore_kwargs)
        logger.info(f"Index built successfully with {len(articles)} articles")

    def get_index_stats(self, db: Session) -> Dict:
        """Get comprehensive statistics about the index and articles"""
        try:
            total_articles = db.query(Article).count()
            articles = db.query(Article).all()

            # Articles by source
            articles_by_source = {}
            for article in articles:
                articles_by_source[article.source] = articles_by_source.get(article.source, 0) + 1

            # Date range
            oldest = db.query(Article).order_by(Article.published_date.asc()).first()
            newest = db.query(Article).order_by(Article.published_date.desc()).first()

            # Last ingested and scraped
            last_ingested = db.query(Article).order_by(Article.created_at.desc()).first()
            last_scraped = db.query(Article).order_by(Article.scraped_at.desc()).first()

            return {
                "total_articles": total_articles,
                "articles_by_source": articles_by_source,
                "date_range": {
                    "oldest": oldest.published_date.isoformat() + "Z" if oldest and oldest.published_date else None,
                    "newest": newest.published_date.isoformat() + "Z" if newest and newest.published_date else None,
                },
                "indexed_articles": self.get_collection_point_count() or 0,
                "last_refresh": last_ingested.created_at.isoformat() + "Z" if last_ingested and last_ingested.created_at else None,
                "last_scraped": last_scraped.scraped_at.isoformat() + "Z" if last_scraped and last_scraped.scraped_at else None,
            }

        except Exception as e:
            logger.error(f"Error getting index stats: {e}")
            return {
                "total_articles": 0,
                "articles_by_source": {},
                "date_range": {"oldest": None, "newest": None},
                "indexed_articles": 0,
                "last_refresh": None,
                "last_scraped": None,
            }


# Singleton instance
_index_service = None


def get_index_service(embedding_service: Optional[EmbeddingService] = None) -> IndexService:
    """Get or create the index service singleton

    Args:
        embedding_service: Optional EmbeddingService instance (for dependency injection/testing)

    Returns:
        IndexService instance
    """
    global _index_service

    # If dependency is provided, create a new instance (for testing/DI)
    if embedding_service is not None:
        return IndexService(embedding_service=embedding_service)

    # Otherwise, use singleton pattern
    if _index_service is None:
        from app.services.embeddings import get_embedding_service
        _index_service = IndexService(embedding_service=get_embedding_service())
    return _index_service
