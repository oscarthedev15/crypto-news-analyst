from typing import Optional
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    """Application settings loaded from environment variables"""
    
    # LLM Provider Settings
    # Supported providers: "ollama", "openai", "auto"
    # "auto" will try Ollama first, then fall back to OpenAI if configured
    llm_provider: str = "auto"
    
    # Ollama Settings (free, local LLM)
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.1:8b"  # Recommended: llama3.1:8b (best balance), qwen2.5:14b (best quality), llama3.2:3b (fastest/lightest)
    ollama_temperature: float = 0.1  # Lower = more focused and deterministic (better for staying on topic)
    ollama_max_tokens: int = 1000  # Increased for more complete responses with citations
    
    # OpenAI Settings (requires API key)
    openai_api_key: Optional[str] = None  # Now optional!
    openai_model: str = "gpt-4o-mini"
    openai_temperature: float = 0.5
    openai_max_tokens: int = 800
    
    # Database
    database_url: str = "sqlite:///./news_articles.db"
    
    # Embedding
    embedding_model: str = "all-MiniLM-L6-v2"
    
    # Search
    top_k_articles: int = 5
    similarity_threshold: float = 0.3
    
    # News sources
    news_sources: list = ["CoinTelegraph", "TheDefiant", "Decrypt"]
    
    # App
    app_title: str = "Crypto News Agent"
    app_description: str = "AI-powered semantic search over crypto news articles"
    log_level: str = "INFO"
    
    class Config:
        env_file = ".env"
        case_sensitive = False

settings = Settings()
