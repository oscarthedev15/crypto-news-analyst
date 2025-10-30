from pydantic import BaseModel, Field
from typing import Optional

class QuestionRequest(BaseModel):
    """Validate user question input"""
    question: str = Field(..., min_length=1, max_length=500)
    
    class Config:
        json_schema_extra = {
            "example": {"question": "What is the latest news about Bitcoin?"}
        }

class IndexStats(BaseModel):
    """Statistics about the search index"""
    total_articles: int
    articles_by_source: dict
    date_range: dict
    last_refresh: Optional[str]  # When articles were last ingested into DB
    last_scraped: Optional[str]  # When articles were last scraped from sources
    indexed_articles: int
