from sqlalchemy import Column, Integer, String, Text, DateTime, LargeBinary, Index
from datetime import datetime
from app.database import Base

class Article(Base):
    """Model for storing cryptocurrency news articles"""
    __tablename__ = "articles"
    
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(500), nullable=False)
    content = Column(Text, nullable=False)
    url = Column(String(1000), unique=True, nullable=False, index=True)
    source = Column(String(100), nullable=False, index=True)  # "CoinTelegraph", "TheDefiant", "Decrypt"
    published_date = Column(DateTime, nullable=False, index=True)  # When article was published
    scraped_at = Column(DateTime, default=datetime.utcnow, nullable=False)  # When we scraped it
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)  # When inserted to DB
    embedding = Column(LargeBinary, nullable=True)  # Vector embedding (binary format)
    
    def __repr__(self):
        return f"<Article(id={self.id}, title='{self.title[:50]}...', source='{self.source}', published={self.published_date})>"
    
    def to_dict(self):
        """Convert to dictionary for JSON serialization"""
        return {
            "id": self.id,
            "title": self.title,
            "content": self.content,
            "url": self.url,
            "source": self.source,
            "published_date": self.published_date.isoformat() + "Z" if self.published_date else None,
            "scraped_at": self.scraped_at.isoformat() + "Z" if self.scraped_at else None,
            "created_at": self.created_at.isoformat() + "Z" if self.created_at else None,
        }

# Create indexes
Index('idx_source_published', Article.source, Article.published_date)
