import logging
from typing import List, Tuple, Optional, Dict
from datetime import datetime
from sqlalchemy.orm import Session

from langchain_qdrant import (
    QdrantVectorStore,
    RetrievalMode,
    FastEmbedSparse,
)
from langchain_core.documents import Document
from qdrant_client import QdrantClient

from app.models import Article
from app.services.embeddings import EmbeddingService
from app.config import settings

logger = logging.getLogger(__name__)

COLLECTION_NAME = "crypto_news_articles"


class SearchService:
    """Service for semantic search using LangChain Qdrant with hybrid search (dense + sparse)"""
    
    def __init__(self, embedding_service: EmbeddingService):
        self.vectorstore = None
        self.embedding_service = embedding_service
        self.sparse_embeddings = None
        self._index_point_count = None
        self.qdrant_client = None

        # Initialize Qdrant client for server connection
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
            logger.info("Initialized FastEmbed sparse embeddings for hybrid search")
        except Exception as e:
            logger.error(
                f"Failed to initialize sparse embeddings: {e}. This will degrade search quality. "
                f"Please ensure fastembed>=0.2.0 is installed correctly."
            )
    
    def build_index(self, db: Session):
        """Build Qdrant semantic search index using LangChain with hybrid search
        
        REQUIRES: Hybrid search (dense + sparse embeddings) - will fail if sparse embeddings unavailable
        """
        logger.info("Building semantic search index with LangChain Qdrant (hybrid search)...")
        
        # Ensure sparse embeddings are available - hybrid search is required
        if not self.sparse_embeddings:
            error_msg = (
                "Cannot build index: Sparse embeddings not available. "
                "Hybrid search is required for index building. "
                "Please ensure fastembed>=0.2.0 is installed correctly. "
                "Install with: pip install fastembed>=0.2.0"
            )
            logger.error(error_msg)
            raise RuntimeError(error_msg)
        
        articles = db.query(Article).all()
        if not articles:
            logger.warning("No articles found to index")
            return
        
        logger.info(f"Indexing {len(articles)} articles...")
        
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
        
        logger.info("Building Qdrant vector store with hybrid search (dense + sparse)...")
        
        # Always recreate collection when rebuilding the index to avoid duplicate points
        if self.qdrant_client:
            try:
                collections = self.qdrant_client.get_collections().collections
                collection_exists = any(c.name == COLLECTION_NAME for c in collections)
                if collection_exists:
                    logger.info(
                        f"Collection '{COLLECTION_NAME}' exists. Deleting to ensure a clean rebuild (prevents duplicate points)."
                    )
                    self.qdrant_client.delete_collection(COLLECTION_NAME)
                    logger.info("Collection deleted. It will be recreated with hybrid search support.")
            except Exception as e:
                logger.warning(f"Error checking/deleting existing collection: {e}. Continuing with build...")
        
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
        self.vectorstore = QdrantVectorStore.from_documents(**vectorstore_kwargs)
        logger.info("Built index with hybrid search - combining semantic and keyword matching")
        
        logger.info(f"Semantic index built successfully. Indexed {len(articles)} articles.")
        
        # Update point count after building index
        self._index_point_count = self._get_collection_point_count()
    
    def _get_collection_point_count(self) -> Optional[int]:
        """Get the current point count of the collection"""
        try:
            if not self.qdrant_client:
                return None
            # Get collection info which includes point count
            collection_info = self.qdrant_client.get_collection(COLLECTION_NAME)
            if collection_info:
                return collection_info.points_count
            return None
        except Exception as e:
            logger.debug(f"Error getting collection point count: {e}")
            return None
    
    def _should_reload_index(self) -> bool:
        """Check if collection has changed by comparing point count"""
        if self.vectorstore is None or self._index_point_count is None:
            return True
        
        current_point_count = self._get_collection_point_count()
        if current_point_count is None:
            return False
        
        return current_point_count != self._index_point_count
    
    def _build_load_kwargs(self, include_sparse: bool = False) -> dict:
        """Build kwargs for loading Qdrant vectorstore"""
        load_kwargs = {
            "embedding": self.embedding_service.langchain_embeddings,
            "collection_name": COLLECTION_NAME,
            "url": settings.qdrant_url,
            "vector_name": "dense",
        }
        
        if include_sparse and self.sparse_embeddings:
            load_kwargs.update({
                "sparse_embedding": self.sparse_embeddings,
                "retrieval_mode": RetrievalMode.HYBRID,
                "sparse_vector_name": "sparse",
            })
        
        if settings.qdrant_api_key:
            load_kwargs["api_key"] = settings.qdrant_api_key
        
        return load_kwargs
    
    def load_index(self) -> bool:
        """Load Qdrant vectorstore from server
        
        Tries to load with hybrid search first (if sparse embeddings available),
        falls back to dense-only if that fails or sparse embeddings unavailable.
        """
        try:
            # Check if collection exists
            if not self.qdrant_client:
                logger.error("Qdrant client not initialized")
                return False
            
            collections = self.qdrant_client.get_collections().collections
            collection_exists = any(c.name == COLLECTION_NAME for c in collections)
            
            if not collection_exists:
                logger.warning(f"Qdrant collection '{COLLECTION_NAME}' not found on server")
                return False

            # Try hybrid search first if sparse embeddings are available
            if self.sparse_embeddings:
                try:
                    load_kwargs = self._build_load_kwargs(include_sparse=True)
                    self.vectorstore = QdrantVectorStore.from_existing_collection(**load_kwargs)
                    logger.info("Loaded vectorstore with hybrid search (dense + sparse)")
                except Exception as e:
                    error_msg = str(e)
                    if "does not contain sparse vectors" in error_msg:
                        logger.warning(
                            f"Collection exists but lacks sparse vectors for hybrid search. "
                            f"To enable hybrid search, rebuild the index: POST /api/rebuild-index"
                        )
                    else:
                        logger.warning(f"Failed to load with hybrid search: {e}. Trying dense-only mode...")
                    
                    # Fall back to dense-only if hybrid load fails
                    load_kwargs = self._build_load_kwargs(include_sparse=False)
                    self.vectorstore = QdrantVectorStore.from_existing_collection(**load_kwargs)
                    logger.info("Loaded vectorstore with dense-only search")
            else:
                logger.warning("Loading with dense-only search (sparse embeddings unavailable)")
                load_kwargs = self._build_load_kwargs(include_sparse=False)
                self.vectorstore = QdrantVectorStore.from_existing_collection(**load_kwargs)
            
            # Store current point count to detect future changes
            self._index_point_count = self._get_collection_point_count()
            num_docs = self._index_point_count or 0
            logger.info(f"Loaded Qdrant vectorstore with {num_docs} articles")
            
            return True
        except Exception as e:
            logger.error(f"Error loading indexes: {e}")
            return False
    
    def search(
        self,
        query: str,
        db: Session,
        top_k: int = 8,
        date_filter: Optional[datetime] = None
    ) -> List[Tuple[Article, float]]:
        """Semantic search using LangChain Qdrant vectorstore with hybrid search
        
        Args:
            query: Search query string
            db: SQLAlchemy session
            top_k: Number of results to return
            date_filter: Only return articles after this date
            
        Returns:
            List of (Article, score) tuples
        """
        # Check if index needs to be reloaded
        if self._should_reload_index():
            logger.info("Detected index update, reloading index...")
            if self.load_index():
                logger.info("Index reloaded successfully")
            else:
                logger.warning("Failed to reload index")
        
        if self.vectorstore is None:
            logger.warning("Search index not loaded")
            return []
        
        try:
            # Get document count from Qdrant for limiting search results
            max_docs = self._get_collection_point_count() or 1000  # Fallback to 1000 if unavailable
            # Get semantic results with scores using hybrid search
            semantic_docs_with_scores = self.vectorstore.similarity_search_with_score(
                query, 
                k=min(top_k * 2, max_docs)
            )
            
            results = []
            seen_article_ids = set()
            
            best_score = semantic_docs_with_scores[0][1] if semantic_docs_with_scores else 1.0
            
            duplicates_skipped = 0
            for doc, score in semantic_docs_with_scores:
                article_id = doc.metadata.get("id")
                if not article_id:
                    continue
                
                # Skip if we've already seen this article ID
                if article_id in seen_article_ids:
                    duplicates_skipped += 1
                    continue
                
                article = db.query(Article).filter(Article.id == article_id).first()
                if article is None:
                    continue
                
                # Apply date filter
                if date_filter and article.published_date:
                    if article.published_date < date_filter:
                        continue
                
                # Normalize scores: top result = 100%, others scale proportionally
                normalized_score = (score / best_score) if best_score > 0 else score
                normalized_score = min(1.0, normalized_score)
                
                results.append((article, float(normalized_score)))
                seen_article_ids.add(article_id)
            
            if duplicates_skipped > 0:
                logger.warning(f"Skipped {duplicates_skipped} duplicate articles in search results")
            
            # Sort by score (descending), then by date (descending)
            results.sort(key=lambda x: (
                -x[1],
                -x[0].created_at.timestamp() if x[0].created_at else 0,
                -x[0].published_date.timestamp() if x[0].published_date else 0
            ))
            
            logger.info(f"Hybrid search returned {len(results[:top_k])} results")
            
            return results[:top_k]
        
        except Exception as e:
            logger.error(f"Error during search: {e}")
            return []
    
    def get_index_stats(self, db: Session) -> Dict:
        """Get statistics about indexed articles"""
        try:
            if self._should_reload_index():
                logger.info("Detected index update, reloading index for stats...")
                if self.load_index():
                    logger.info("Index reloaded successfully")
            
            if self.vectorstore is None:
                return {
                    "total_articles": 0,
                    "articles_by_source": {},
                    "date_range": {"oldest": None, "newest": None},
                    "indexed_articles": 0,
                    "last_refresh": None,
                    "last_scraped": None,
                }
            
            total_articles = db.query(Article).count()
            articles = db.query(Article).all()
            
            articles_by_source = {}
            for article in articles:
                articles_by_source[article.source] = articles_by_source.get(article.source, 0) + 1
            
            oldest = db.query(Article).order_by(Article.published_date.asc()).first()
            newest = db.query(Article).order_by(Article.published_date.desc()).first()
            last_ingested = db.query(Article).order_by(Article.created_at.desc()).first()
            last_scraped = db.query(Article).order_by(Article.scraped_at.desc()).first()
            
            return {
                "total_articles": total_articles,
                "articles_by_source": articles_by_source,
                "date_range": {
                    "oldest": oldest.published_date.isoformat() + "Z" if oldest and oldest.published_date else None,
                    "newest": newest.published_date.isoformat() + "Z" if newest and newest.published_date else None,
                },
                "indexed_articles": self._get_collection_point_count() or 0,
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