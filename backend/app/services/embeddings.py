from sentence_transformers import SentenceTransformer
from functools import lru_cache
import numpy as np
from typing import List
import logging

logger = logging.getLogger(__name__)

class EmbeddingService:
    """Service for generating text embeddings using sentence-transformers"""
    
    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        self.model_name = model_name
        self.model = self._load_model()
        self.dimension = self.get_embedding_dimension()
    
    @lru_cache(maxsize=1)
    def _load_model(self) -> SentenceTransformer:
        """Load and cache the sentence-transformers model"""
        logger.info(f"Loading embedding model: {self.model_name}")
        model = SentenceTransformer(self.model_name)
        logger.info(f"Model loaded successfully. Dimension: {model.get_sentence_embedding_dimension()}")
        return model
    
    def generate_embedding(self, text: str) -> np.ndarray:
        """Generate embedding for a single text string
        
        Args:
            text: Text to embed
            
        Returns:
            numpy array of shape (384,)
        """
        if not text or not isinstance(text, str):
            return np.zeros(self.dimension, dtype=np.float32)
        
        try:
            embedding = self.model.encode(text, convert_to_numpy=True)
            return embedding.astype(np.float32)
        except Exception as e:
            logger.error(f"Error generating embedding: {e}")
            return np.zeros(self.dimension, dtype=np.float32)
    
    def generate_embeddings_batch(self, texts: List[str]) -> np.ndarray:
        """Generate embeddings for multiple texts efficiently
        
        Args:
            texts: List of texts to embed
            
        Returns:
            numpy array of shape (len(texts), 384)
        """
        if not texts:
            return np.zeros((0, self.dimension), dtype=np.float32)
        
        try:
            # Filter out invalid texts
            valid_texts = [t if isinstance(t, str) else "" for t in texts]
            
            # Generate embeddings
            embeddings = self.model.encode(
                valid_texts,
                convert_to_numpy=True,
                show_progress_bar=False
            )
            
            return embeddings.astype(np.float32)
        except Exception as e:
            logger.error(f"Error generating batch embeddings: {e}")
            return np.zeros((len(texts), self.dimension), dtype=np.float32)
    
    def get_embedding_dimension(self) -> int:
        """Get the dimension of embeddings produced by this model"""
        return self.model.get_sentence_embedding_dimension()


# Singleton instance
_embedding_service = None

def get_embedding_service(model_name: str = "all-MiniLM-L6-v2") -> EmbeddingService:
    """Get or create the embedding service singleton"""
    global _embedding_service
    if _embedding_service is None:
        _embedding_service = EmbeddingService(model_name)
    return _embedding_service
