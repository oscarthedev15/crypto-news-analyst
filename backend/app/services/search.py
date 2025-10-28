import faiss
import numpy as np
import pickle
import logging
import re
from pathlib import Path
from typing import List, Tuple, Optional, Dict
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from rank_bm25 import BM25Okapi
from app.models import Article
from app.services.embeddings import get_embedding_service

logger = logging.getLogger(__name__)

DATA_DIR = Path("data")
INDEX_FILE = DATA_DIR / "faiss.index"
ARTICLE_IDS_FILE = DATA_DIR / "article_ids.pkl"
METADATA_FILE = DATA_DIR / "article_metadata.pkl"
BM25_INDEX_FILE = DATA_DIR / "bm25.pkl"

class SearchService:
    """Service for hybrid search using FAISS (semantic) + BM25 (keyword)"""
    
    def __init__(self):
        self.index = None
        self.article_ids = None
        self.metadata = None
        self.bm25 = None
        self.tokenized_corpus = None
        self.embedding_service = get_embedding_service()
    
    def _tokenize(self, text: str) -> List[str]:
        """Enhanced tokenization for BM25 with domain/brand name handling
        
        Args:
            text: Text to tokenize
            
        Returns:
            List of lowercase tokens with normalized variations
        """
        text_lower = text.lower()
        
        # Extract basic tokens (keep dots for domains like "pump.fun")
        tokens = re.findall(r'\b[\w.]+\b', text_lower)
        
        # Add normalized variations for tokens with dots
        # This handles cases like "pump.fun" vs "pumpfun"
        normalized_tokens = []
        for token in tokens:
            normalized_tokens.append(token)
            # If token contains dot, also add version without dots
            if '.' in token:
                no_dot = token.replace('.', '')
                if no_dot:  # Only add if non-empty
                    normalized_tokens.append(no_dot)
            # Also add version with dots for tokens that might be written with dots
            # e.g., "pumpfun" could be "pump.fun"
            elif len(token) > 6:  # Only for longer tokens
                # Common patterns: add dot before last 3-4 chars (e.g., "pumpfun" → "pump.fun")
                for split_pos in [3, 4]:
                    if len(token) > split_pos:
                        with_dot = token[:split_pos] + '.' + token[split_pos:]
                        normalized_tokens.append(with_dot)
        
        return list(set(normalized_tokens))  # Remove duplicates
    
    def build_index(self, db: Session):
        """Build FAISS (semantic) and BM25 (keyword) indexes from all articles in database
        
        Args:
            db: SQLAlchemy session
        """
        logger.info("Building hybrid search indexes (FAISS + BM25)...")
        
        # Create data directory if it doesn't exist
        DATA_DIR.mkdir(exist_ok=True)
        
        # Query all articles
        articles = db.query(Article).all()
        if not articles:
            logger.warning("No articles found to index")
            return
        
        logger.info(f"Indexing {len(articles)} articles...")
        
        # Generate embeddings for all articles (FAISS)
        texts = [f"{a.title} {a.content}" for a in articles]
        embeddings = self.embedding_service.generate_embeddings_batch(texts)
        
        # Create FAISS index (semantic search)
        dimension = embeddings.shape[1]
        self.index = faiss.IndexFlatL2(dimension)
        self.index.add(embeddings)
        
        # Build BM25 index (keyword search)
        logger.info("Building BM25 keyword index...")
        self.tokenized_corpus = [self._tokenize(text) for text in texts]
        self.bm25 = BM25Okapi(self.tokenized_corpus)
        
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
        with open(BM25_INDEX_FILE, 'wb') as f:
            pickle.dump({'bm25': self.bm25, 'tokenized_corpus': self.tokenized_corpus}, f)
        
        logger.info(f"Hybrid indexes built successfully. Indexed {len(articles)} articles.")
    
    def load_index(self) -> bool:
        """Load FAISS and BM25 indexes from disk
        
        Returns:
            True if successful, False otherwise
        """
        try:
            required_files = [INDEX_FILE, ARTICLE_IDS_FILE, METADATA_FILE]
            if not all(f.exists() for f in required_files):
                logger.warning("Index files not found")
                return False
            
            # Load FAISS index
            self.index = faiss.read_index(str(INDEX_FILE))
            
            with open(ARTICLE_IDS_FILE, 'rb') as f:
                self.article_ids = pickle.load(f)
            
            with open(METADATA_FILE, 'rb') as f:
                self.metadata = pickle.load(f)
            
            # Load BM25 index (if available)
            if BM25_INDEX_FILE.exists():
                with open(BM25_INDEX_FILE, 'rb') as f:
                    bm25_data = pickle.load(f)
                    self.bm25 = bm25_data['bm25']
                    self.tokenized_corpus = bm25_data['tokenized_corpus']
                logger.info(f"Loaded hybrid indexes (FAISS + BM25) with {len(self.article_ids)} articles")
            else:
                logger.warning("BM25 index not found - using semantic search only. Run index rebuild to enable hybrid search.")
                logger.info(f"Loaded FAISS index with {len(self.article_ids)} articles")
            
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
        keyword_boost: float = 0.3
    ) -> List[Tuple[Article, float]]:
        """Hybrid search combining semantic (FAISS) and keyword (BM25) matching
        
        Args:
            query: Search query string
            db: SQLAlchemy session
            top_k: Number of results to return
            date_filter: Only return articles after this date
            keyword_boost: Weight for keyword matching (0.0-1.0). Default 0.3 means 70% semantic, 30% keyword
            
        Returns:
            List of (Article, hybrid_score) tuples
        """
        if self.index is None:
            logger.warning("Search index not loaded")
            return []
        
        try:
            # Generate embedding for query (semantic search)
            query_embedding = self.embedding_service.generate_embedding(query)
            
            if query_embedding is None or np.all(query_embedding == 0):
                logger.warning("Could not generate embedding for query")
                return []
            
            # FAISS semantic search
            distances, indices = self.index.search(
                np.array([query_embedding], dtype=np.float32),
                min(top_k * 4, len(self.article_ids))  # Get more results for hybrid ranking
            )
            
            # Convert distances to similarity scores (0-1 range)
            # L2 distance: lower = more similar
            semantic_scores = 1 / (1 + distances[0])
            
            # BM25 keyword search (if available)
            bm25_scores = None
            if self.bm25 is not None:
                tokenized_query = self._tokenize(query)
                bm25_raw_scores = self.bm25.get_scores(tokenized_query)
                # Normalize BM25 scores to 0-1 range
                max_bm25 = max(bm25_raw_scores) if len(bm25_raw_scores) > 0 else 1.0
                if max_bm25 > 0:
                    bm25_scores = bm25_raw_scores / max_bm25
                else:
                    bm25_scores = bm25_raw_scores
            
            # Combine scores using hybrid weighting
            results = []
            threshold = 0.25  # Lower threshold for hybrid search
            
            for idx, semantic_score in zip(indices[0], semantic_scores):
                # Calculate hybrid score
                if bm25_scores is not None:
                    bm25_score = bm25_scores[idx]
                    # Weighted combination: (1 - keyword_boost) * semantic + keyword_boost * keyword
                    hybrid_score = (1 - keyword_boost) * semantic_score + keyword_boost * bm25_score
                else:
                    # Fall back to semantic only
                    hybrid_score = semantic_score
                
                if hybrid_score < threshold:
                    continue
                
                article_id = int(self.article_ids[idx])
                article = db.query(Article).filter(Article.id == article_id).first()
                
                if article is None:
                    continue
                
                # Apply date filter if provided
                if date_filter and article.published_date:
                    if article.published_date < date_filter:
                        continue
                
                results.append((article, float(hybrid_score)))
            
            # Sort by hybrid score (primary), then by created_at (newer first), then by published_date
            results.sort(key=lambda x: (
                -x[1],  # Hybrid score (higher is better)
                -x[0].created_at.timestamp() if x[0].created_at else 0,  # Newer in DB first
                -x[0].published_date.timestamp() if x[0].published_date else 0  # Then by published date
            ))
            
            mode = "hybrid (semantic + keyword)" if bm25_scores is not None else "semantic only"
            logger.info(f"Search mode: {mode}, returned {len(results[:top_k])} results")
            
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
