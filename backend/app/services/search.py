import logging
from typing import List, Tuple, Optional
from datetime import datetime
from sqlalchemy.orm import Session

from langchain_qdrant import QdrantVectorStore, RetrievalMode, FastEmbedSparse
from qdrant_client import QdrantClient

from app.models import Article
from app.services.embeddings import EmbeddingService
from app.config import settings

logger = logging.getLogger(__name__)

COLLECTION_NAME = "crypto_news_articles"


class SearchService:
    """Service for semantic search over crypto news articles

    Responsibilities:
    - Loading vector store from Qdrant
    - Performing hybrid semantic search
    - Returning ranked article results

    Used by: RAG agent, API endpoints
    """

    def __init__(self, embedding_service: EmbeddingService):
        self.embedding_service = embedding_service
        self.vectorstore = None
        self.sparse_embeddings = None
        self.qdrant_client = None
        self._cached_point_count = None

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
            logger.warning(f"Sparse embeddings unavailable: {e}. Will use dense-only search.")

    def _collection_exists(self) -> bool:
        """Check if collection exists in Qdrant"""
        try:
            collections = self.qdrant_client.get_collections().collections
            return any(c.name == COLLECTION_NAME for c in collections)
        except Exception as e:
            logger.error(f"Error checking collection: {e}")
            return False

    def _get_point_count(self) -> int:
        """Get current point count from collection"""
        try:
            if not self._collection_exists():
                return 0
            collection_info = self.qdrant_client.get_collection(COLLECTION_NAME)
            return collection_info.points_count if collection_info else 0
        except Exception as e:
            logger.debug(f"Error getting point count: {e}")
            return 0

    def _should_reload(self) -> bool:
        """Check if vectorstore needs reloading based on point count changes"""
        if self.vectorstore is None:
            return True

        current_count = self._get_point_count()
        if self._cached_point_count is None or current_count != self._cached_point_count:
            logger.info(f"Point count changed: {self._cached_point_count} → {current_count}")
            return True

        return False

    def load_index(self) -> bool:
        """Load vectorstore from existing Qdrant collection

        Returns:
            True if loaded successfully, False otherwise
        """
        try:
            if not self._collection_exists():
                logger.warning(f"Collection '{COLLECTION_NAME}' not found in Qdrant")
                return False

            # Build load kwargs
            load_kwargs = {
                "embedding": self.embedding_service.langchain_embeddings,
                "collection_name": COLLECTION_NAME,
                "url": settings.qdrant_url,
                "vector_name": "dense",
            }

            # Try hybrid search if sparse embeddings available
            if self.sparse_embeddings:
                try:
                    load_kwargs.update({
                        "sparse_embedding": self.sparse_embeddings,
                        "retrieval_mode": RetrievalMode.HYBRID,
                        "sparse_vector_name": "sparse",
                    })
                    if settings.qdrant_api_key:
                        load_kwargs["api_key"] = settings.qdrant_api_key

                    self.vectorstore = QdrantVectorStore.from_existing_collection(**load_kwargs)
                    logger.info("Loaded vectorstore with hybrid search")
                except Exception as e:
                    if "does not contain sparse vectors" in str(e):
                        logger.warning("Collection lacks sparse vectors, falling back to dense-only")
                    else:
                        logger.warning(f"Hybrid search failed: {e}, falling back to dense-only")

                    # Fall back to dense-only
                    load_kwargs = {
                        "embedding": self.embedding_service.langchain_embeddings,
                        "collection_name": COLLECTION_NAME,
                        "url": settings.qdrant_url,
                        "vector_name": "dense",
                    }
                    if settings.qdrant_api_key:
                        load_kwargs["api_key"] = settings.qdrant_api_key
                    self.vectorstore = QdrantVectorStore.from_existing_collection(**load_kwargs)
                    logger.info("Loaded vectorstore with dense-only search")
            else:
                # Dense-only mode
                if settings.qdrant_api_key:
                    load_kwargs["api_key"] = settings.qdrant_api_key
                self.vectorstore = QdrantVectorStore.from_existing_collection(**load_kwargs)
                logger.info("Loaded vectorstore with dense-only search")

            # Cache point count
            self._cached_point_count = self._get_point_count()
            logger.info(f"Vectorstore loaded with {self._cached_point_count} documents")
            return True

        except Exception as e:
            logger.error(f"Error loading vectorstore: {e}")
            return False

    def search(
        self,
        query: str,
        db: Session,
        top_k: int = 8,
        date_filter: Optional[datetime] = None
    ) -> List[Tuple[Article, float]]:
        """Perform semantic search over articles

        Args:
            query: Search query string
            db: Database session
            top_k: Number of results to return
            date_filter: Optional date filter (articles after this date)

        Returns:
            List of (Article, normalized_score) tuples, sorted by relevance
        """
        # Auto-reload if needed
        if self._should_reload():
            logger.info("Auto-reloading vectorstore...")
            if not self.load_index():
                logger.error("Failed to load vectorstore")
                return []

        if self.vectorstore is None:
            logger.warning("Vectorstore not loaded")
            return []

        try:
            # Get more results than needed to handle deduplication
            fetch_count = min(top_k * 2, self._cached_point_count or 100)

            # Perform similarity search
            docs_with_scores = self.vectorstore.similarity_search_with_score(
                query,
                k=fetch_count
            )

            if not docs_with_scores:
                logger.info("No results found")
                return []

            # Extract article IDs
            article_ids = []
            score_map = {}
            for doc, score in docs_with_scores:
                article_id = doc.metadata.get("id")
                if article_id and article_id not in score_map:
                    article_ids.append(article_id)
                    score_map[article_id] = score

            # Batch fetch articles from database (fixes N+1 query problem)
            articles_by_id = {
                article.id: article
                for article in db.query(Article).filter(Article.id.in_(article_ids)).all()
            }

            # Build results with proper score normalization
            results = []
            min_score = min(score_map.values())
            max_score = max(score_map.values())
            score_range = max_score - min_score if max_score > min_score else 1.0

            for article_id in article_ids:
                article = articles_by_id.get(article_id)
                if not article:
                    continue

                # Apply date filter
                if date_filter and article.published_date:
                    if article.published_date < date_filter:
                        continue

                # Normalize score: best match = 1.0, worst match = 0.0
                raw_score = score_map[article_id]
                normalized_score = 1.0 - ((raw_score - min_score) / score_range)
                normalized_score = max(0.0, min(1.0, normalized_score))

                results.append((article, float(normalized_score)))

            # Sort by score descending, then by date descending
            results.sort(key=lambda x: (
                -x[1],  # Score (higher is better)
                -x[0].published_date.timestamp() if x[0].published_date else 0,
            ))

            # Return top_k results
            final_results = results[:top_k]
            logger.info(f"Search returned {len(final_results)} results for query: {query[:50]}...")
            return final_results

        except Exception as e:
            logger.error(f"Error during search: {e}", exc_info=True)
            return []


# Singleton instance
_search_service = None


def get_search_service(embedding_service: Optional[EmbeddingService] = None) -> SearchService:
    """Get or create the search service singleton

    Args:
        embedding_service: Optional EmbeddingService instance (for dependency injection/testing)

    Returns:
        SearchService instance
    """
    global _search_service

    # If dependency is provided, create a new instance (for testing/DI)
    if embedding_service is not None:
        return SearchService(embedding_service=embedding_service)

    # Otherwise, use singleton pattern
    if _search_service is None:
        from app.services.embeddings import get_embedding_service
        _search_service = SearchService(embedding_service=get_embedding_service())
    return _search_service
