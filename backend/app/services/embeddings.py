import logging
from langchain_huggingface import HuggingFaceEmbeddings
from app.config import settings

logger = logging.getLogger(__name__)


class EmbeddingService:
    """Embeddings service using LangChain HuggingFaceEmbeddings wrapper"""
    
    def __init__(self, model_name: str = None):
        """Initialize embedding service
        
        Args:
            model_name: Name of the sentence-transformers model to use (defaults to config)
        """
        self.model_name = model_name or settings.embedding_model
        logger.info(f"Loading embedding model: {self.model_name}")
        
        self.langchain_embeddings = HuggingFaceEmbeddings(
            model_name=self.model_name,
            model_kwargs={'device': 'cpu'},
            encode_kwargs={'normalize_embeddings': True}
        )
        logger.info("Model loaded successfully")


# Singleton instance
_embedding_service = None


def get_embedding_service(model_name: str = None) -> EmbeddingService:
    """Get or create the embedding service singleton"""
    global _embedding_service
    if _embedding_service is None:
        _embedding_service = EmbeddingService(model_name)
    return _embedding_service
