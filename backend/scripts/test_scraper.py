#!/usr/bin/env python
"""
Test script to fetch ONE article from a given source.
Useful for debugging scraper functionality.

Usage:
    python scripts/test_scraper.py --source CoinDesk
    python scripts/test_scraper.py --source CoinTelegraph
    python scripts/test_scraper.py --source Decrypt
    python scripts/test_scraper.py --source TheBlock
"""

import sys
import asyncio
import argparse
import logging
from pathlib import Path
from datetime import datetime
import json

# Add parent directory to path so we can import app modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.scraper import (
    CoinTelegraphScraper,
    TheDefiantScraper,
    DecryptScraper
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


async def test_scraper(source: str):
    """Test a scraper by fetching one article
    
    Args:
        source: News source name
    """
    # Map source name to scraper class
    scrapers_map = {
        "CoinTelegraph": CoinTelegraphScraper,
        "TheDefiant": TheDefiantScraper,
        "Decrypt": DecryptScraper,
    }
    
    if source not in scrapers_map:
        logger.error(f"Unknown source: {source}")
        logger.info(f"Available sources: {', '.join(scrapers_map.keys())}")
        return False
    
    scraper_class = scrapers_map[source]
    logger.info(f"Testing {source} scraper...")
    
    scraper = scraper_class()
    
    try:
        # Fetch one article
        articles = await scraper.fetch_articles(max_articles=1)
        
        if not articles:
            logger.warning(f"No articles found from {source}")
            return False
        
        article = articles[0]
        
        # Print article details
        print("\n" + "="*80)
        print(f"SUCCESS: Retrieved article from {source}")
        print("="*80)
        print(f"\nTitle: {article['title']}")
        print(f"\nURL: {article['url']}")
        print(f"\nSource: {article['source']}")
        print(f"\nPublished Date: {article['published_date']}")
        print(f"\nContent Length: {len(article['content'])} characters")
        print(f"\nContent Preview:")
        print("-"*80)
        preview = article['content'][:500] + "..." if len(article['content']) > 500 else article['content']
        print(preview)
        print("-"*80)
        
        # Save full article to JSON file
        output_file = f"test_article_{source}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(output_file, 'w') as f:
            json.dump(article, f, indent=2, default=str)
        print(f"\nFull article saved to: {output_file}")
        print("="*80 + "\n")
        
        return True
    
    except Exception as e:
        logger.error(f"Error testing scraper: {e}", exc_info=True)
        return False
    
    finally:
        await scraper.close()


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description="Test a crypto news scraper")
    parser.add_argument(
        "--source",
        type=str,
        required=True,
        choices=["CoinTelegraph", "TheDefiant", "Decrypt"],
        help="News source to test"
    )
    
    args = parser.parse_args()
    
    # Run async test
    success = asyncio.run(test_scraper(args.source))
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()

