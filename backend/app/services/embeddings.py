from sentence_transformers import SentenceTransformer
from langchain_core.embeddings import Embeddings
import logging

logger = logging.getLogger(__name__)


class EmbeddingService(Embeddings):
    """Custom LangChain-compatible embeddings using sentence-transformers
    
    This wraps sentence-transformers in a LangChain-compatible interface
    """
    
    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        """Initialize embedding service
        
        Args:
            model_name: Name of the sentence-transformers model to use
        """
        self.model_name = model_name
        logger.info(f"Loading embedding model: {self.model_name}")
        
        # Use sentence-transformers directly (stable, no segfaults)
        self.model = SentenceTransformer(model_name)
        logger.info(f"Model loaded successfully")
    
    def embed_query(self, text: str) -> list:
        """Generate embedding for a query text (LangChain interface)
        
        Args:
            text: Text to embed
            
        Returns:
            List of floats representing the embedding
        """
        if not text or not isinstance(text, str):
            logger.warning("Empty or invalid text provided for embedding")
            return []
        
        try:
            embedding = self.model.encode(text, convert_to_numpy=True)
            return embedding.tolist()
        except Exception as e:
            logger.error(f"Error generating query embedding: {e}")
            return []
    
    def embed_documents(self, texts: list) -> list:
        """Generate embeddings for multiple documents (LangChain interface)
        
        Args:
            texts: List of texts to embed
            
        Returns:
            List of embeddings (each embedding is a list of floats)
        """
        if not texts:
            return []
        
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
            
            # Convert to list of lists for LangChain compatibility
            return [emb.tolist() for emb in embeddings]
        except Exception as e:
            logger.error(f"Error generating batch embeddings: {e}")
            return []


# Singleton instance
_embedding_service = None


def get_embedding_service(model_name: str = "all-MiniLM-L6-v2") -> EmbeddingService:
    """Get or create the embedding service singleton"""
    global _embedding_service
    if _embedding_service is None:
        _embedding_service = EmbeddingService(model_name)
    return _embedding_service
