from pydantic import BaseModel, Field
from typing import Optional

class QuestionRequest(BaseModel):
    """Validate user question input"""
    question: str = Field(..., min_length=5, max_length=500)
    
    class Config:
        json_schema_extra = {
            "example": {"question": "What is the latest news about Bitcoin?"}
        }

class ArticleSchema(BaseModel):
    """Schema for article responses"""
    id: int
    title: str
    content: str
    url: str
    source: str
    published_date: Optional[str]
    scraped_at: Optional[str]
    created_at: Optional[str]
    
    class Config:
        from_attributes = True

class IndexStats(BaseModel):
    """Statistics about the search index"""
    total_articles: int
    articles_by_source: dict
    date_range: dict
    last_refresh: Optional[str]  # When articles were last ingested into DB
    last_scraped: Optional[str]  # When articles were last scraped from sources
    indexed_articles: int
