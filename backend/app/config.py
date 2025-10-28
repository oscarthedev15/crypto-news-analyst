import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    """Application settings loaded from environment variables"""
    
    # OpenAI
    openai_api_key: str
    
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
