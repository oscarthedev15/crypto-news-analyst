import faiss
import numpy as np
import pickle
import logging
from pathlib import Path
from typing import List, Tuple, Optional, Dict
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from app.models import Article
from app.services.embeddings import get_embedding_service

logger = logging.getLogger(__name__)

DATA_DIR = Path("data")
INDEX_FILE = DATA_DIR / "faiss.index"
ARTICLE_IDS_FILE = DATA_DIR / "article_ids.pkl"
METADATA_FILE = DATA_DIR / "article_metadata.pkl"

class SearchService:
    """Service for semantic search using FAISS"""
    
    def __init__(self):
        self.index = None
        self.article_ids = None
        self.metadata = None
        self.embedding_service = get_embedding_service()
    
    def build_index(self, db: Session):
        """Build FAISS index from all articles in database
        
        Args:
            db: SQLAlchemy session
        """
        logger.info("Building FAISS index...")
        
        # Create data directory if it doesn't exist
        DATA_DIR.mkdir(exist_ok=True)
        
        # Query all articles
        articles = db.query(Article).all()
        if not articles:
            logger.warning("No articles found to index")
            return
        
        logger.info(f"Indexing {len(articles)} articles...")
        
        # Generate embeddings for all articles
        texts = [f"{a.title} {a.content}" for a in articles]
        embeddings = self.embedding_service.generate_embeddings_batch(texts)
        
        # Create FAISS index
        dimension = embeddings.shape[1]
        self.index = faiss.IndexFlatL2(dimension)
        self.index.add(embeddings)
        
        # Store article IDs and metadata
        self.article_ids = np.array([a.id for a in articles], dtype=np.int64)
        self.metadata = {}
        
        for i, article in enumerate(articles):
            self.metadata[int(self.article_ids[i])] = {
                "source": article.source,
                "published_date": article.published_date.isoformat() + "Z" if article.published_date else None,
                "scraped_at": article.scraped_at.isoformat() + "Z" if article.scraped_at else None,
                "created_at": article.created_at.isoformat() + "Z" if article.created_at else None,
                "title": article.title,
            }
        
        # Save to disk
        faiss.write_index(self.index, str(INDEX_FILE))
        with open(ARTICLE_IDS_FILE, 'wb') as f:
            pickle.dump(self.article_ids, f)
        with open(METADATA_FILE, 'wb') as f:
            pickle.dump(self.metadata, f)
        
        logger.info(f"Index built successfully. Indexed {len(articles)} articles.")
    
    def load_index(self) -> bool:
        """Load FAISS index from disk
        
        Returns:
            True if successful, False otherwise
        """
        try:
            if not all([INDEX_FILE.exists(), ARTICLE_IDS_FILE.exists(), METADATA_FILE.exists()]):
                logger.warning("FAISS index files not found")
                return False
            
            self.index = faiss.read_index(str(INDEX_FILE))
            
            with open(ARTICLE_IDS_FILE, 'rb') as f:
                self.article_ids = pickle.load(f)
            
            with open(METADATA_FILE, 'rb') as f:
                self.metadata = pickle.load(f)
            
            logger.info(f"Loaded FAISS index with {len(self.article_ids)} articles")
            return True
        except Exception as e:
            logger.error(f"Error loading FAISS index: {e}")
            return False
    
    def search(
        self,
        query: str,
        db: Session,
        top_k: int = 5,
        date_filter: Optional[datetime] = None
    ) -> List[Tuple[Article, float]]:
        """Search for articles similar to the query
        
        Args:
            query: Search query string
            db: SQLAlchemy session
            top_k: Number of results to return
            date_filter: Only return articles after this date
            
        Returns:
            List of (Article, similarity_score) tuples
        """
        if self.index is None:
            logger.warning("Search index not loaded")
            return []
        
        try:
            # Generate embedding for query
            query_embedding = self.embedding_service.generate_embedding(query)
            
            if query_embedding is None or np.all(query_embedding == 0):
                logger.warning("Could not generate embedding for query")
                return []
            
            # Search index
            distances, indices = self.index.search(
                np.array([query_embedding], dtype=np.float32),
                top_k * 2  # Get more results for filtering
            )
            
            # Convert distances to similarity scores
            # L2 distance: lower = more similar
            # Score: 1 / (1 + distance)
            scores = 1 / (1 + distances[0])
            
            # Filter by similarity threshold and gather results
            results = []
            threshold = 0.3  # Minimum similarity threshold
            
            for idx, score in zip(indices[0], scores):
                if score < threshold:
                    continue
                
                article_id = int(self.article_ids[idx])
                article = db.query(Article).filter(Article.id == article_id).first()
                
                if article is None:
                    continue
                
                # Apply date filter if provided
                if date_filter and article.published_date:
                    if article.published_date < date_filter:
                        continue
                
                results.append((article, float(score)))
            
            # Sort by score (primary), then by created_at (when added to DB - newer first), then by published_date
            # This prioritizes newer additions to the database
            results.sort(key=lambda x: (
                -x[1],  # Similarity score (higher is better)
                -x[0].created_at.timestamp() if x[0].created_at else 0,  # Newer in DB first
                -x[0].published_date.timestamp() if x[0].published_date else 0  # Then by published date
            ))
            
            return results[:top_k]
        
        except Exception as e:
            logger.error(f"Error during search: {e}")
            return []
    
    def get_index_stats(self, db: Session) -> Dict:
        """Get statistics about indexed articles
        
        Args:
            db: SQLAlchemy session
            
        Returns:
            Dictionary with index statistics
        """
        try:
            if self.index is None:
                return {
                    "total_articles": 0,
                    "articles_by_source": {},
                    "date_range": {"oldest": None, "newest": None},
                    "indexed_articles": 0,
                    "last_refresh": None,
                    "last_scraped": None,
                }
            
            # Query all articles
            total_articles = db.query(Article).count()
            articles = db.query(Article).all()
            
            # Count by source
            articles_by_source = {}
            for article in articles:
                articles_by_source[article.source] = articles_by_source.get(article.source, 0) + 1
            
            # Get date range
            oldest = db.query(Article).order_by(Article.published_date.asc()).first()
            newest = db.query(Article).order_by(Article.published_date.desc()).first()
            
            # Get the most recent created_at time (when articles were ingested into DB)
            last_ingested = db.query(Article).order_by(Article.created_at.desc()).first()
            last_scraped = db.query(Article).order_by(Article.scraped_at.desc()).first()
            
            return {
                "total_articles": total_articles,
                "articles_by_source": articles_by_source,
                "date_range": {
                    "oldest": oldest.published_date.isoformat() + "Z" if oldest and oldest.published_date else None,
                    "newest": newest.published_date.isoformat() + "Z" if newest and newest.published_date else None,
                },
                "indexed_articles": len(self.article_ids) if self.article_ids is not None else 0,
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
