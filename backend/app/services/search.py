import logging
from pathlib import Path
from typing import List, Tuple, Optional, Dict
from datetime import datetime
from sqlalchemy.orm import Session

from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document

from app.models import Article
from app.services.embeddings import get_embedding_service

logger = logging.getLogger(__name__)

DATA_DIR = Path("data")
VECTORSTORE_DIR = DATA_DIR / "faiss_vectorstore"


class SearchService:
    """Service for semantic search using LangChain FAISS"""
    
    def __init__(self):
        self.vectorstore = None
        self.embedding_service = get_embedding_service()
        self.article_ids_map = {}  # Map from LangChain doc ID to article ID
        self._index_load_time = None
    
    def build_index(self, db: Session):
        """Build FAISS semantic search index using LangChain"""
        logger.info("Building semantic search index with LangChain FAISS...")
        
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
        
        # Build FAISS vector store with LangChain
        logger.info("Building FAISS vector store...")
        self.vectorstore = FAISS.from_documents(
            documents,
            embedding=self.embedding_service.langchain_embeddings
        )
        
        # Save vectorstore to disk
        self.vectorstore.save_local(str(VECTORSTORE_DIR))
        
        # Save article IDs mapping
        import pickle
        with open(DATA_DIR / "article_ids_map.pkl", 'wb') as f:
            pickle.dump(self.article_ids_map, f)
        
        logger.info(f"Semantic index built successfully. Indexed {len(articles)} articles.")
    
    def _get_index_modification_time(self) -> Optional[float]:
        """Get the latest modification time of index files"""
        try:
            if not VECTORSTORE_DIR.exists():
                return None
            return VECTORSTORE_DIR.stat().st_mtime
        except Exception as e:
            logger.error(f"Error checking index modification time: {e}")
            return None
    
    def _should_reload_index(self) -> bool:
        """Check if index files have been modified since last load"""
        if self.vectorstore is None or self._index_load_time is None:
            return True
        
        current_mod_time = self._get_index_modification_time()
        if current_mod_time is None:
            return False
        
        return current_mod_time > self._index_load_time
    
    def load_index(self, force: bool = False) -> bool:
        """Load FAISS vectorstore from disk"""
        try:
            if not VECTORSTORE_DIR.exists():
                logger.warning("Vectorstore index not found")
                return False
            
            # Load FAISS vectorstore
            self.vectorstore = FAISS.load_local(
                str(VECTORSTORE_DIR),
                embeddings=self.embedding_service.langchain_embeddings,
                allow_dangerous_deserialization=True
            )
            
            # Load article IDs mapping
            import pickle
            ids_map_file = DATA_DIR / "article_ids_map.pkl"
            if ids_map_file.exists():
                with open(ids_map_file, 'rb') as f:
                    self.article_ids_map = pickle.load(f)
            
            self._index_load_time = self._get_index_modification_time()
            num_docs = len(self.article_ids_map)
            logger.info(f"Loaded FAISS vectorstore with {num_docs} articles")
            
            return True
        except Exception as e:
            logger.error(f"Error loading indexes: {e}")
            return False
    
    def search(
        self,
        query: str,
        db: Session,
        top_k: int = 5,
        date_filter: Optional[datetime] = None,
        keyword_boost: float = 0.3  # Kept for API compatibility, but not used
    ) -> List[Tuple[Article, float]]:
        """Semantic search using LangChain FAISS vectorstore
        
        Args:
            query: Search query string
            db: SQLAlchemy session
            top_k: Number of results to return
            date_filter: Only return articles after this date
            keyword_boost: Deprecated parameter (kept for API compatibility)
            
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
            # Get semantic results with scores
            semantic_docs_with_scores = self.vectorstore.similarity_search_with_score(
                query, 
                k=min(top_k * 2, len(self.article_ids_map))
            )
            
            # Convert to (Article, score) tuples
            results = []
            
            # Calculate cosine similarity scores (for normalized embeddings)
            # FAISS returns L2 distance, but for normalized embeddings:
            # cosine_similarity ≈ 1 - (L2² / 2)
            # We'll normalize relative to best match for intuitive percentages
            if semantic_docs_with_scores:
                best_distance = semantic_docs_with_scores[0][1]
                # For normalized embeddings, typical L2 distances are small (0-2)
                # Best match typically has distance ~0.1-0.3, good matches ~0.3-0.6
            else:
                best_distance = 0
            
            for doc, distance in semantic_docs_with_scores:
                article_id = doc.metadata.get("id")
                if not article_id:
                    continue
                
                article = db.query(Article).filter(Article.id == article_id).first()
                if article is None:
                    continue
                
                # Apply date filter
                if date_filter and article.published_date:
                    if article.published_date < date_filter:
                        continue
                
                # Convert L2 distance to cosine similarity
                # Math: For normalized embeddings, ||a-b||² = 2(1 - cos(θ))
                # So: cosine_similarity = 1 - (distance² / 2)
                cosine_similarity = max(0.0, min(1.0, 1.0 - (distance ** 2) / 2.0))
                
                # Get the best match's cosine similarity for normalization
                best_cosine_sim = 1.0 - (best_distance ** 2) / 2.0 if best_distance > 0 else 1.0
                best_cosine_sim = max(0.0, min(1.0, best_cosine_sim))
                
                # Normalize scores so top result gets 100%, others scale proportionally
                # This makes percentages intuitive: best match = 100%, others relative to it
                if best_cosine_sim > 0:
                    score = cosine_similarity / best_cosine_sim
                    score = min(1.0, score)  # Cap at 100%
                else:
                    score = cosine_similarity
                
                results.append((article, float(score)))
            
            # Sort by score (higher is better), then by date
            results.sort(key=lambda x: (
                -x[1],  # Score
                -x[0].created_at.timestamp() if x[0].created_at else 0,
                -x[0].published_date.timestamp() if x[0].published_date else 0
            ))
            
            logger.info(f"Semantic search returned {len(results[:top_k])} results")
            
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
