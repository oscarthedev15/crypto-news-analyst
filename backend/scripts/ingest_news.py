#!/usr/bin/env python
"""
News ingestion script to fetch and store articles in the database.
Run periodically via cron job or manually.

Usage:
    python scripts/ingest_news.py --max-articles-per-source 25
    python scripts/ingest_news.py --force-rebuild-index
"""

import sys
import asyncio
import argparse
import logging
from pathlib import Path
from datetime import datetime

# Add parent directory to path so we can import app modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.database import SessionLocal, init_db
from app.models import Article
from app.services.scraper import scrape_all_sources, APPROVED_SOURCES
from app.services.search import get_search_service

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


async def ingest_articles(max_articles: int = 20, force_rebuild: bool = False):
    """Fetch and ingest articles from all sources
    
    Args:
        max_articles: Max NEW articles per source to fetch
        force_rebuild: Force rebuild of FAISS index
    """
    logger.info(f"Starting article ingestion (max {max_articles} NEW per source)...")
    
    # Initialize database
    init_db()
    db = SessionLocal()
    
    try:
        # Get all existing URLs from database to avoid re-scraping
        logger.info("Fetching existing article URLs from database...")
        existing_urls = set(url[0] for url in db.query(Article.url).all())
        logger.info(f"Found {len(existing_urls)} existing articles in database")
        
        # Fetch NEW articles from all sources (passing existing URLs to skip)
        logger.info("Scraping NEW articles from all sources...")
        start_time = datetime.utcnow()
        articles_data = await scrape_all_sources(max_articles, existing_urls)
        logger.info(f"Scraped {len(articles_data)} NEW articles in {(datetime.utcnow() - start_time).total_seconds():.1f}s")
        
        # Process and store articles
        new_count = 0
        skipped_count = 0
        
        for article_data in articles_data:
            try:
                # Double-check URL doesn't exist (should already be filtered by scraper)
                if article_data["url"] in existing_urls:
                    logger.debug(f"Skipping duplicate URL: {article_data['url']}")
                    skipped_count += 1
                    continue
                
                # Create new article
                article = Article(
                    title=article_data["title"],
                    content=article_data["content"],
                    url=article_data["url"],
                    source=article_data["source"],
                    published_date=article_data["published_date"],
                    scraped_at=datetime.utcnow()
                )
                db.add(article)
                new_count += 1
                
                # Add to existing_urls set to prevent duplicates in this batch
                existing_urls.add(article_data["url"])
            
            except Exception as e:
                logger.warning(f"Error processing article: {e}")
                skipped_count += 1
                continue
        
        # Commit changes
        db.commit()
        logger.info(f"Ingestion complete: {new_count} new, {skipped_count} skipped")
        
        # Print statistics by source (dynamically from scraper config)
        logger.info("Articles by source:")
        for source_name in APPROVED_SOURCES.values():
            count = db.query(Article).filter(Article.source == source_name).count()
            logger.info(f"  {source_name}: {count}")
        
        # Total articles
        total = db.query(Article).count()
        logger.info(f"Total articles in database: {total}")
        
        # Rebuild FAISS index
        logger.info("Rebuilding FAISS index...")
        search_service = get_search_service()
        search_service.build_index(db)
        logger.info("FAISS index rebuilt successfully")
        
        # Print index statistics
        stats = search_service.get_index_stats(db)
        logger.info(f"Index statistics:")
        logger.info(f"  Indexed articles: {stats['indexed_articles']}")
        logger.info(f"  Date range: {stats['date_range']['oldest']} to {stats['date_range']['newest']}")
        
        logger.info("Database refresh completed successfully")
        print(f"\n✓ Refresh completed at {datetime.utcnow().isoformat()}")
        print(f"  New articles: {new_count}")
        print(f"  Skipped: {skipped_count}")
        print(f"  Total in DB: {total}")
    
    except Exception as e:
        logger.error(f"Error during ingestion: {e}", exc_info=True)
        print(f"\n✗ Error during ingestion: {e}")
        return False
    
    finally:
        db.close()
    
    return True


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description="Ingest crypto news articles")
    parser.add_argument(
        "--max-articles-per-source",
        type=int,
        default=20,
        help="Maximum articles to fetch per source (default: 20)"
    )
    parser.add_argument(
        "--force-rebuild-index",
        action="store_true",
        help="Force rebuild of FAISS index"
    )
    
    args = parser.parse_args()
    
    # Run async ingestion
    success = asyncio.run(ingest_articles(args.max_articles_per_source, args.force_rebuild_index))
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
