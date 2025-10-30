import logging
from pathlib import Path
from typing import List, Tuple, Optional, Dict
from datetime import datetime
from uuid import uuid4
from sqlalchemy.orm import Session

from langchain_qdrant import (
    QdrantVectorStore,
    RetrievalMode,
    FastEmbedSparse,
)
from langchain_core.documents import Document
from qdrant_client import QdrantClient

from app.models import Article
from app.services.embeddings import get_embedding_service
from app.config import settings

logger = logging.getLogger(__name__)

# Use path relative to this file's location
# This file is at: backend/app/services/search.py
# Data directory is at: backend/data/
DATA_DIR = Path(__file__).parent.parent.parent / "data"
COLLECTION_NAME = "crypto_news_articles"


class SearchService:
    """Service for semantic search using LangChain Qdrant with hybrid search (dense + sparse)"""
    
    def __init__(self):
        self.vectorstore = None
        self.embedding_service = get_embedding_service()
        self.sparse_embeddings = None
        self.article_ids_map = {}
        self._index_point_count = None  # Track point count instead of modification time
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
        # Hybrid search provides better results by combining semantic (dense) and keyword (sparse) matching
        try:
            self.sparse_embeddings = FastEmbedSparse(model_name="Qdrant/bm25")
            logger.info("Initialized FastEmbed sparse embeddings for hybrid search")
        except Exception as e:
            logger.error(
                f"Failed to initialize sparse embeddings: {e}. This will degrade search quality. "
                f"Please ensure fastembed>=0.2.0 is installed correctly."
            )
            # Note: We still set sparse_embeddings to None to allow fallback to dense-only mode
            # but this should be rare and indicates a configuration issue
    
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
        
        DATA_DIR.mkdir(exist_ok=True)
        
        articles = db.query(Article).all()
        if not articles:
            logger.warning("No articles found to index")
            return
        
        logger.info(f"Indexing {len(articles)} articles...")
        
        # Prepare documents for LangChain
        documents = []
        self.article_ids_map = {}
        
        for article in articles:
            text = f"{article.title} {article.content}"
            doc_id = f"article_{article.id}"
            
            # Create LangChain Document with metadata
            doc = Document(
                page_content=text,
                metadata={
                    "id": article.id,
                    "title": article.title,
                    "source": article.source,
                    "url": article.url,
                    "published_date": article.published_date.isoformat() + "Z" if article.published_date else None,
                }
            )
            documents.append(doc)
            self.article_ids_map[doc_id] = article.id
        
        # Build Qdrant vector store with hybrid search (required)
        # Hybrid search combines semantic (dense) and keyword (sparse) matching
        logger.info("Building Qdrant vector store with hybrid search (dense + sparse)...")
        vectorstore_kwargs = {
            "documents": documents,
            "embedding": self.embedding_service.langchain_embeddings,
            "sparse_embedding": self.sparse_embeddings,
            "url": settings.qdrant_url,
            "collection_name": COLLECTION_NAME,
            "retrieval_mode": RetrievalMode.HYBRID,
            "vector_name": "dense",
        }
        if settings.qdrant_api_key:
            vectorstore_kwargs["api_key"] = settings.qdrant_api_key
        self.vectorstore = QdrantVectorStore.from_documents(**vectorstore_kwargs)
        logger.info("Built index with hybrid search - combining semantic and keyword matching")
        
        # Save article IDs mapping
        import pickle
        ids_map_file = DATA_DIR / "article_ids_map.pkl"
        with open(ids_map_file, 'wb') as f:
            pickle.dump(self.article_ids_map, f)
        
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
            # If we can't get point count, don't reload (safer)
            return False
        
        # Reload if point count has changed (new articles added)
        return current_point_count != self._index_point_count
    
    def load_index(self, force: bool = False) -> bool:
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
            # This is preferred for better search quality
            if self.sparse_embeddings:
                try:
                    load_kwargs = {
                        "embedding": self.embedding_service.langchain_embeddings,
                        "sparse_embedding": self.sparse_embeddings,
                        "collection_name": COLLECTION_NAME,
                        "url": settings.qdrant_url,
                        "vector_name": "dense",
                    }
                    if settings.qdrant_api_key:
                        load_kwargs["api_key"] = settings.qdrant_api_key
                    self.vectorstore = QdrantVectorStore.from_existing_collection(**load_kwargs)
                    logger.info("Loaded vectorstore with hybrid search (dense + sparse)")
                except Exception as e:
                    logger.warning(
                        f"Failed to load with hybrid search: {e}. "
                        f"Trying dense-only mode..."
                    )
                    # Fall back to dense-only if hybrid load fails
                    # (e.g., collection was built without sparse vectors)
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
                # Dense-only mode (sparse embeddings not available)
                logger.warning("Loading with dense-only search (sparse embeddings unavailable)")
                load_kwargs = {
                    "embedding": self.embedding_service.langchain_embeddings,
                    "collection_name": COLLECTION_NAME,
                    "url": settings.qdrant_url,
                    "vector_name": "dense",
                }
                if settings.qdrant_api_key:
                    load_kwargs["api_key"] = settings.qdrant_api_key
                self.vectorstore = QdrantVectorStore.from_existing_collection(**load_kwargs)
            
            # Load article IDs mapping
            import pickle
            ids_map_file = DATA_DIR / "article_ids_map.pkl"
            if ids_map_file.exists():
                with open(ids_map_file, 'rb') as f:
                    self.article_ids_map = pickle.load(f)
            
            # Store current point count to detect future changes
            self._index_point_count = self._get_collection_point_count()
            num_docs = len(self.article_ids_map)
            logger.info(f"Loaded Qdrant vectorstore with {num_docs} articles")
            
            return True
        except Exception as e:
            logger.error(f"Error loading indexes: {e}")
            return False
    
    def search(
        self,
        query: str,
        db: Session,
        top_k: int = 5,
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
            # Get semantic results with scores using hybrid search
            semantic_docs_with_scores = self.vectorstore.similarity_search_with_score(
                query, 
                k=min(top_k * 2, len(self.article_ids_map))
            )
            
            # Convert to (Article, score) tuples
            results = []
            seen_article_ids = set()  # Track seen article IDs to prevent duplicates
            
            # Qdrant returns similarity scores (higher is better for cosine similarity)
            # Score is already normalized between 0 and 1 for cosine similarity
            if semantic_docs_with_scores:
                best_score = semantic_docs_with_scores[0][1]
            else:
                best_score = 1.0
            
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
                
                # Normalize scores so top result gets 100%, others scale proportionally
                # This makes percentages intuitive: best match = 100%, others relative to it
                if best_score > 0:
                    normalized_score = score / best_score
                    normalized_score = min(1.0, normalized_score)  # Cap at 100%
                else:
                    normalized_score = score
                
                results.append((article, float(normalized_score)))
                seen_article_ids.add(article_id)
            
            if duplicates_skipped > 0:
                logger.warning(f"Skipped {duplicates_skipped} duplicate articles in search results")
            
            # Sort by score (higher is better), then by date
            results.sort(key=lambda x: (
                -x[1],  # Score
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
                "indexed_articles": len(self.article_ids_map) if self.article_ids_map else 0,
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

def get_search_service() -> SearchService:
    """Get or create the search service singleton"""
    global _search_service
    if _search_service is None:
        _search_service = SearchService()
    return _search_service