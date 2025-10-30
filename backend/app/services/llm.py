import logging
import httpx
from app.config import settings

logger = logging.getLogger(__name__)

class LLMService:
    """Service for managing LLM provider initialization and configuration
    
    Supports multiple LLM providers:
    - Ollama (local, free) - default if running
    - OpenAI (cloud, requires API key) - fallback option
    
    Note: The RAG agent handles actual response generation. This service only manages
    LLM initialization and provides access to the langchain_llm instance.
    """
    
    def __init__(self):
        self.provider = None
        self.langchain_llm = None
        self._initialize_llm()
    
    def _check_ollama_health(self) -> bool:
        """Check if Ollama is running and accessible
        
        Returns:
            True if Ollama is running, False otherwise
        """
        try:
            response = httpx.get(f"{settings.ollama_base_url}/api/tags", timeout=2.0)
            return response.status_code == 200
        except Exception as e:
            logger.debug(f"Ollama health check failed: {e}")
            return False
    
    def _initialize_llm(self):
        """Initialize the LLM based on provider settings with smart auto-detection"""
        provider = settings.llm_provider.lower()
        
        # Auto-detection mode: try Ollama first, then OpenAI
        if provider == "auto":
            if self._check_ollama_health():
                logger.info("🤖 Auto-detected Ollama running locally")
                self._setup_ollama()
                return
            elif settings.openai_api_key:
                logger.info("🔑 Ollama not available, falling back to OpenAI")
                self._setup_openai()
                return
            else:
                raise RuntimeError(
                    "❌ No LLM provider available!\n"
                    "Options:\n"
                    "  1. Install Ollama: https://ollama.com/download\n"
                    "  2. Set OPENAI_API_KEY in .env file"
                )
        
        # Explicit provider selection
        elif provider == "ollama":
            if not self._check_ollama_health():
                raise RuntimeError(
                    f"❌ Ollama not running at {settings.ollama_base_url}\n"
                    "Run: ollama serve"
                )
            self._setup_ollama()
        
        elif provider == "openai":
            if not settings.openai_api_key:
                raise RuntimeError(
                    "❌ OpenAI API key not configured\n"
                    "Set OPENAI_API_KEY in .env file"
                )
            self._setup_openai()
        
        else:
            raise ValueError(f"Unknown LLM provider: {provider}")
    
    def _setup_ollama(self):
        """Initialize Ollama LLM"""
        try:
            from langchain_ollama import ChatOllama
            
            self.langchain_llm = ChatOllama(
                model=settings.ollama_model,
                base_url=settings.ollama_base_url,
                temperature=settings.ollama_temperature,
                num_predict=settings.ollama_max_tokens,
            )
            self.provider = "ollama"
            logger.info(f"✅ Initialized Ollama with model: {settings.ollama_model}")
        except ImportError:
            raise RuntimeError(
                "❌ langchain-ollama not installed\n"
                "Run: pip install langchain-ollama"
            )
    
    def _setup_openai(self):
        """Initialize OpenAI LLM"""
        try:
            from langchain_openai import ChatOpenAI
            
            self.langchain_llm = ChatOpenAI(
                model=settings.openai_model,
                temperature=settings.openai_temperature,
                max_tokens=settings.openai_max_tokens,
                streaming=True,
                api_key=settings.openai_api_key
            )
            self.provider = "openai"
            logger.info(f"✅ Initialized OpenAI with model: {settings.openai_model}")
        except ImportError:
            raise RuntimeError(
                "❌ langchain-openai not installed\n"
                "Run: pip install langchain-openai"
            )
    
    def get_provider_info(self) -> dict:
        """Get information about the current LLM provider
        
        Returns:
            Dictionary with provider details
        """
        if self.provider == "ollama":
            return {
                "provider": "ollama",
                "model": settings.ollama_model,
                "base_url": settings.ollama_base_url,
                "cost": "free"
            }
        elif self.provider == "openai":
            return {
                "provider": "openai",
                "model": settings.openai_model,
                "cost": "paid"
            }
        return {"provider": "unknown"}


# Singleton instance
_llm_service = None

def get_llm_service() -> LLMService:
    """Get or create the LLM service singleton"""
    global _llm_service
    if _llm_service is None:
        _llm_service = LLMService()
    return _llm_service
