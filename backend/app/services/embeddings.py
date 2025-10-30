from sentence_transformers import SentenceTransformer
from langchain_huggingface import HuggingFaceEmbeddings
import numpy as np
import logging
from app.config import settings

logger = logging.getLogger(__name__)


class EmbeddingService:
    """Embeddings service using LangChain HuggingFaceEmbeddings wrapper
    
    Provides efficient embedding generation with LangChain integration
    """
    
    def __init__(self, model_name: str = None):
        """Initialize embedding service
        
        Args:
            model_name: Name of the sentence-transformers model to use (defaults to config)
        """
        self.model_name = model_name or settings.embedding_model
        logger.info(f"Loading embedding model: {self.model_name}")
        
        # Use LangChain's HuggingFaceEmbeddings from langchain-huggingface package
        # This is the updated, non-deprecated version
        self.langchain_embeddings = HuggingFaceEmbeddings(
            model_name=self.model_name,
            model_kwargs={'device': 'cpu'},
            encode_kwargs={'normalize_embeddings': True}
        )
        
        # Keep direct access for compatibility
        self.model = SentenceTransformer(self.model_name)
        logger.info(f"Model loaded successfully (dim: {self.model.get_sentence_embedding_dimension()})")
    
    def generate_embedding(self, text: str) -> 'numpy.ndarray':
        """Generate embedding for a single text (used by SearchService)
        
        Args:
            text: Text to embed
            
        Returns:
            Numpy array representing the embedding
        """
        if not text or not isinstance(text, str):
            logger.warning("Empty or invalid text provided for embedding")
            return np.array([])
        
        try:
            embedding = self.model.encode(text, convert_to_numpy=True, normalize_embeddings=True)
            return embedding
        except Exception as e:
            logger.error(f"Error generating embedding: {e}")
            return np.array([])
    
    def generate_embeddings_batch(self, texts: list) -> 'numpy.ndarray':
        """Generate embeddings for multiple texts (used by SearchService)
        
        Args:
            texts: List of texts to embed
            
        Returns:
            Numpy array of embeddings (shape: [num_texts, embedding_dim])
        """
        if not texts:
            return np.array([])
        
        try:
            # Filter out invalid texts
            valid_texts = [t if isinstance(t, str) and t else "" for t in texts]
            
            # Generate embeddings in batch
            embeddings = self.model.encode(
                valid_texts,
                convert_to_numpy=True,
                show_progress_bar=False,
                normalize_embeddings=True
            )
            
            # Return as numpy array for SearchService compatibility
            return embeddings
        except Exception as e:
            logger.error(f"Error generating batch embeddings: {e}")
            return np.array([])


# Singleton instance
_embedding_service = None


def get_embedding_service(model_name: str = None) -> EmbeddingService:
    """Get or create the embedding service singleton"""
    global _embedding_service
    if _embedding_service is None:
        _embedding_service = EmbeddingService(model_name)
    return _embedding_service
