"""
Modular news scraper service with source validation and duplicate prevention.
Site-aware implementation that understands each source's URL structure.

Design Principles:
-----------------
1. SITE-AWARE: Validates URLs based on known patterns for each source
2. CONFIGURATION-DRIVEN: Add new sources by updating config dicts
3. PATTERN-BASED: Uses site-specific URL validation for accuracy
4. DUPLICATE-AWARE: Skips articles already in database

How to Add a New Source:
------------------------
STEP 1: Analyze the website structure
   - Visit the site and examine article URLs
   - Identify the article URL pattern (e.g., /news/[long-slug])
   - Note category/aggregation pages to avoid (e.g., /news/defi, /markets)
   - Check how path depth indicates article vs category

STEP 2: Add configuration
   1. Add domain to APPROVED_SOURCES dict with display name
   2. Add homepage URL to SOURCE_HOMEPAGES (where to start scraping)
   3. Add URL pattern to SOURCE_PATTERNS (how to identify real articles)

Example:
    APPROVED_SOURCES = {
        "example-news.com": "ExampleNews",
    }
    
    SOURCE_HOMEPAGES = {
        "example-news.com": "https://example-news.com/latest/",
    }
    
    SOURCE_PATTERNS = {
        "example-news.com": {
            "article_prefixes": ["/news/", "/articles/"],  # Valid article path prefixes
            "min_slug_length": 20,  # Minimum chars in final slug (articles are descriptive)
            "excluded_segments": ["defi", "markets", "opinion"],  # Category names to skip
        }
    }

Key Obstacle: Website Structure Understanding
---------------------------------------------
Different news sites organize content differently:
- Some use /news/[article-slug] (CoinTelegraph)
- Others use /articles/[category]/[article-slug] (DLNews)
- Path depth alone isn't enough - need to check slug length and category names
- Short segments (< 15 chars) are usually categories, not article titles
"""

import logging
import asyncio
import httpx
from typing import List, Dict, Optional, Set
from datetime import datetime, timedelta
from dateutil import parser as date_parser
from bs4 import BeautifulSoup
from urllib.parse import urlparse, urljoin

logger = logging.getLogger(__name__)

# Configuration for approved crypto news sources
APPROVED_SOURCES = {
    "cointelegraph.com": "CoinTelegraph",
    "thedefiant.io": "TheDefiant",
    "dlnews.com": "DLNews",
}

# Custom homepage URLs for sources (where to start scraping)
SOURCE_HOMEPAGES = {
    "cointelegraph.com": "https://cointelegraph.com/category/latest-news",
    "thedefiant.io": "https://thedefiant.io/",
    "dlnews.com": "https://www.dlnews.com/articles/",
}

# Site-specific URL patterns for accurate article identification
# This is the key to avoiding category pages and finding real articles
SOURCE_PATTERNS = {
    "cointelegraph.com": {
        # CoinTelegraph: Articles are /news/[long-descriptive-slug]
        # Example: /news/don-t-buy-the-meme-warns-cz-as-bizarre-golden-statue-memecoin-crashes-86
        "article_prefixes": ["/news/"],
        "excluded_prefixes": ["/magazine/", "/learn/", "/price-indexes/", "/people/", "/category/"],
        "min_path_segments": 2,  # Must be at least /news/slug
        "min_slug_length": 20,  # Article slugs are long and descriptive
    },
    "dlnews.com": {
        # DLNews: Articles are /articles/[category]/[long-slug]
        # Example: /articles/opinion/code-is-law-documentary-is-worth-a-watch-despite-omissions
        # Example: /articles/markets/the-fed-seen-to-cut-twice-in-2025-what-it-means-for-crypto
        "article_prefixes": ["/articles/"],
        "min_path_segments": 3,  # Must be at least /articles/category/slug
        "min_slug_length": 20,  # Last segment must be a long article slug
        # Category pages are like /articles/defi/ or /articles/markets/ (only 2 segments)
    },
    "thedefiant.io": {
        # TheDefiant: Articles are /news/[category]/[long-slug]
        # Example: /news/defi/tokenized-nasdaq-futures-enter-top-10-by-volume-on-hyperliquid
        "article_prefixes": ["/news/"],
        "excluded_prefixes": ["/podcasts-and-videos/"],
        "min_path_segments": 3,  # Must be at least /news/category/slug
        "min_slug_length": 20,  # Last segment must be a long article slug
        # Category pages are like /news/defi/ (short slug after category)
    },
}

# Headers to avoid bot detection (mimics real browser)
DEFAULT_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
    'Accept-Encoding': 'gzip, deflate, br',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1',
    'Sec-Fetch-Dest': 'document',
    'Sec-Fetch-Mode': 'navigate',
    'Sec-Fetch-Site': 'none',
    'Sec-Fetch-User': '?1',
    'Cache-Control': 'max-age=0',
}


def is_approved_source(url: str) -> bool:
    """Check if URL is from an approved source
    
    Args:
        url: URL to check
        
    Returns:
        True if URL is from an approved source, False otherwise
    """
    for domain in APPROVED_SOURCES.keys():
        if domain in url:
            return True
    return False


def get_source_name(url: str) -> Optional[str]:
    """Get the source name for a given URL
    
    Args:
        url: URL to check
        
    Returns:
        Source name if URL is approved, None otherwise
    """
    for domain, name in APPROVED_SOURCES.items():
        if domain in url:
            return name
    return None


def get_domain(url: str) -> str:
    """Extract domain from URL
    
    Args:
        url: URL to parse
        
    Returns:
        Domain name
    """
    parsed = urlparse(url)
    return parsed.netloc.replace('www.', '')


def looks_like_article(url: str, base_domain: str) -> bool:
    """Site-aware validation to determine if URL is an article (not a category/tag/author page)
    
    Uses SOURCE_PATTERNS configuration to validate URLs based on known patterns for each source.
    
    Args:
        url: URL to check
        base_domain: Base domain of the site (e.g., "cointelegraph.com")
        
    Returns:
        True if URL matches the article pattern for this source
    """
    # Must be from the same domain
    if base_domain not in url:
        return False
    
    # Get pattern config for this source
    if base_domain not in SOURCE_PATTERNS:
        logger.warning(f"No URL pattern configured for {base_domain}, using fallback validation")
        return _fallback_article_check(url)
    
    pattern = SOURCE_PATTERNS[base_domain]
    
    # Parse URL
    parsed = urlparse(url)
    path = parsed.path.strip('/')
    
    # Empty path = homepage
    if not path:
        return False
    
    # Check if path starts with any excluded prefix (e.g., /magazine/, /podcasts-and-videos/)
    if "excluded_prefixes" in pattern:
        for excluded in pattern["excluded_prefixes"]:
            if path.startswith(excluded.lstrip('/')):
                logger.debug(f"URL excluded by prefix {excluded}: {url}")
                return False
    
    # Check if path starts with a valid article prefix (e.g., /news/, /articles/)
    if "article_prefixes" in pattern:
        has_valid_prefix = any(
            path.startswith(prefix.lstrip('/'))
            for prefix in pattern["article_prefixes"]
        )
        if not has_valid_prefix:
            logger.debug(f"URL missing required prefix: {url}")
            return False
    
    # Check minimum path segments (depth)
    path_segments = [seg for seg in path.split('/') if seg]
    min_segments = pattern.get("min_path_segments", 2)
    
    if len(path_segments) < min_segments:
        logger.debug(f"URL has {len(path_segments)} segments, need {min_segments}: {url}")
        return False
    
    # Check last segment (the article slug) is long enough
    # Real articles have descriptive slugs, categories have short names
    last_segment = path_segments[-1]
    min_slug_length = pattern.get("min_slug_length", 15)
    
    if len(last_segment) < min_slug_length:
        logger.debug(f"URL slug too short ({len(last_segment)} < {min_slug_length}): {url}")
        return False
    
    # All checks passed - this looks like an article
    return True


def _fallback_article_check(url: str) -> bool:
    """Fallback heuristic for sources without specific patterns configured
    
    Args:
        url: URL to check
        
    Returns:
        True if URL appears to be an article
    """
    parsed = urlparse(url)
    path = parsed.path.lower().strip('/')
    
    if not path:
        return False
    
    path_segments = [seg for seg in path.split('/') if seg]
    
    # Need at least 2 segments
    if len(path_segments) < 2:
        return False
    
    # Last segment should be reasonably long (descriptive article slug)
    if len(path_segments[-1]) < 20:
        return False
    
    return True


def extract_article_content(soup: BeautifulSoup) -> str:
    """Generic article content extraction - works across different news sites
    
    Args:
        soup: BeautifulSoup object
        
    Returns:
        Cleaned article text
    """
    # Remove unwanted elements
    for element in soup.find_all(['nav', 'header', 'footer', 'script', 'style', 'aside', 'iframe', 'form']):
        element.decompose()
    
    # Remove elements with common noise classes/ids
    noise_patterns = [
        'nav', 'menu', 'sidebar', 'advertisement', 'ad-', 'banner',
        'cookie', 'newsletter', 'subscribe', 'subscription',
        'social', 'share', 'comment', 'related', 'recommend',
        'footer', 'header', 'popup', 'modal', 'overlay'
    ]
    
    for pattern in noise_patterns:
        # Remove by class
        for element in soup.find_all(attrs={'class': lambda x: x and pattern in ' '.join(x).lower() if isinstance(x, list) else pattern in x.lower() if isinstance(x, str) else False}):
            element.decompose()
        # Remove by id
        for element in soup.find_all(attrs={'id': lambda x: x and pattern in x.lower() if isinstance(x, str) else False}):
            element.decompose()
    
    # Try to find main article content container (in order of preference)
    article_container = None
    
    # 1. Look for <article> tag
    article_container = soup.find('article')
    
    # 2. Look for common article content divs
    if not article_container:
        article_container = soup.find('div', {'class': lambda x: x and any(
            keyword in ' '.join(x).lower() if isinstance(x, list) else keyword in x.lower() if isinstance(x, str) else False
            for keyword in ['article-body', 'article-content', 'post-content', 'entry-content', 'story-body', 'prose', 'content-body']
        )})
    
    # 3. Look for <main> tag
    if not article_container:
        article_container = soup.find('main')
    
    # 4. Fallback to body
    if not article_container:
        article_container = soup.find('body')
    
    if not article_container:
        return ""
    
    # Extract all paragraphs
    paragraphs = article_container.find_all('p')
    
    content_parts = []
    for p in paragraphs:
        text = p.get_text(strip=True)
        
        # Filter out short paragraphs (likely navigation/labels)
        if len(text) < 30:
            continue
        
        # Filter out common noise
        text_lower = text.lower()
        noise_keywords = [
            'advertisement', 'sponsored', 'subscribe', 'newsletter',
            'cookie policy', 'privacy policy', 'terms of service',
            'follow us', 'share this', 'sign up', 'sign in',
            'read more about', 'related articles', 'recommended for you',
            'stored on filecoin'  # Crypto-specific noise
        ]
        
        if any(keyword in text_lower for keyword in noise_keywords):
            continue
        
        content_parts.append(text)
    
    return ' '.join(content_parts)


def extract_article_title(soup: BeautifulSoup) -> Optional[str]:
    """Generic title extraction
    
    Args:
        soup: BeautifulSoup object
        
    Returns:
        Article title or None
    """
    # Try h1
    title_elem = soup.find('h1')
    if title_elem:
        return title_elem.get_text(strip=True)
    
    # Try og:title meta tag
    meta_title = soup.find('meta', {'property': 'og:title'})
    if meta_title:
        return meta_title.get('content', '').strip()
    
    # Try title tag
    title_tag = soup.find('title')
    if title_tag:
        title = title_tag.get_text(strip=True)
        # Remove site name suffixes (e.g., "Article Title | Site Name")
        if '|' in title:
            title = title.split('|')[0].strip()
        if ' - ' in title:
            title = title.split(' - ')[0].strip()
        return title
    
    return None


def parse_article_date(soup: BeautifulSoup) -> datetime:
    """Generic date extraction
    
    Args:
        soup: BeautifulSoup object of article page
        
    Returns:
        Parsed datetime object (defaults to now if not found)
    """
    # Try <time> element with datetime attribute
    date_elem = soup.find('time')
    if date_elem and date_elem.get('datetime'):
        try:
            return date_parser.parse(date_elem.get('datetime')).replace(tzinfo=None)
        except:
            pass
    
    # Try meta tags
    meta_date = soup.find('meta', {'property': 'article:published_time'})
    if meta_date:
        try:
            return date_parser.parse(meta_date.get('content', '')).replace(tzinfo=None)
        except:
            pass
    
    meta_date = soup.find('meta', {'name': 'publish-date'})
    if meta_date:
        try:
            return date_parser.parse(meta_date.get('content', '')).replace(tzinfo=None)
        except:
            pass
    
    # Try text in time element
    if date_elem:
        date_str = date_elem.get_text(strip=True)
        try:
            # Handle relative dates like "2 hours ago"
            if "ago" in date_str.lower():
                parts = date_str.lower().split()
                try:
                    value = int(parts[0])
                    unit = parts[1]
                    
                    if "minute" in unit:
                        return datetime.utcnow() - timedelta(minutes=value)
                    elif "hour" in unit:
                        return datetime.utcnow() - timedelta(hours=value)
                    elif "day" in unit:
                        return datetime.utcnow() - timedelta(days=value)
                    elif "week" in unit:
                        return datetime.utcnow() - timedelta(weeks=value)
                    elif "month" in unit:
                        return datetime.utcnow() - timedelta(days=value*30)
                except:
                    pass
            
            # Parse absolute date
            return date_parser.parse(date_str, fuzzy=True).replace(tzinfo=None)
        except:
            pass
    
    # Default to current time
    return datetime.utcnow()


async def fetch_articles_from_source(
    domain: str,
    max_articles: int = 20,
    existing_urls: Optional[Set[str]] = None,
    rate_limit: float = 1.0
) -> List[Dict]:
    """Fetch articles from a single source
    
    Args:
        domain: Source domain (e.g., "cointelegraph.com")
        max_articles: Maximum number of NEW articles to fetch
        existing_urls: Set of URLs already in database (to skip)
        rate_limit: Seconds to wait between requests
        
    Returns:
        List of article dictionaries
    """
    if domain not in APPROVED_SOURCES:
        logger.warning(f"Source {domain} not in approved sources")
        return []
    
    source_name = APPROVED_SOURCES[domain]
    # Use custom homepage if specified, otherwise default to root domain
    homepage = SOURCE_HOMEPAGES.get(domain, f"https://{domain}/")
    
    existing_urls = existing_urls or set()
    articles = []
    
    logger.info(f"Fetching articles from {source_name} ({homepage})")
    
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True, headers=DEFAULT_HEADERS) as client:
            # Fetch homepage
            logger.debug(f"Fetching homepage: {homepage}")
            response = await client.get(homepage)
            response.raise_for_status()
            
            logger.debug(f"Homepage fetched (status: {response.status_code}, size: {len(response.text)} bytes)")
            
            # Parse HTML
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Find ALL links on the page
            potential_article_links = []
            seen_urls = set()
            
            for link in soup.find_all('a', href=True):
                href = link.get('href')
                
                # Make absolute URL
                if href.startswith('//'):
                    href = 'https:' + href
                elif href.startswith('/'):
                    # Use the homepage's base URL to preserve www. prefix if needed
                    parsed_homepage = urlparse(homepage)
                    href = f"{parsed_homepage.scheme}://{parsed_homepage.netloc}{href}"
                elif not href.startswith('http'):
                    href = urljoin(homepage, href)
                
                # Normalize URL (remove fragments, trailing slashes)
                href = href.split('#')[0].split('?')[0].rstrip('/')
                
                # Skip if already seen
                if href in seen_urls:
                    continue
                seen_urls.add(href)
                
                # Must be from our approved source
                if not is_approved_source(href):
                    continue
                
                # Extract clean domain from both the config and the URL for comparison
                url_domain = get_domain(href)
                if url_domain != domain:
                    continue
                
                # Skip if already in database
                if href in existing_urls:
                    continue
                
                # Check if it looks like an article using generic heuristics
                if looks_like_article(href, domain):
                    potential_article_links.append(href)
            
            logger.info(f"Found {len(potential_article_links)} potential NEW article links on {source_name} homepage")
            
            # Track rejection reasons for debugging
            rejections = {"title": 0, "content": 0, "http_error": 0, "other": 0}
            
            # Fetch each article until we have enough
            for url in potential_article_links[:max_articles * 3]:  # Try more than needed in case some fail
                if len(articles) >= max_articles:
                    break
                
                try:
                    logger.debug(f"Fetching article: {url}")
                    
                    # Rate limiting
                    await asyncio.sleep(rate_limit)
                    
                    article_response = await client.get(url)
                    article_response.raise_for_status()
                    
                    article_soup = BeautifulSoup(article_response.text, 'html.parser')
                    
                    # Extract title
                    title = extract_article_title(article_soup)
                    
                    if not title or len(title) < 10:
                        logger.debug(f"Skipping article with invalid title: {url}")
                        rejections["title"] += 1
                        continue
                    
                    # Extract content
                    content = extract_article_content(article_soup)
                    
                    if len(content) < 100:
                        logger.debug(f"Skipping article with insufficient content ({len(content)} chars): {url}")
                        rejections["content"] += 1
                        continue
                    
                    # Extract date
                    published_date = parse_article_date(article_soup)
                    
                    articles.append({
                        "title": title,
                        "content": content,
                        "url": url,
                        "source": source_name,
                        "published_date": published_date,
                    })
                    
                    logger.debug(f"✓ Successfully scraped: {title[:60]}...")
                    
                except httpx.HTTPStatusError as e:
                    if e.response.status_code == 403:
                        logger.warning(f"403 Forbidden for {url} - site may be blocking scrapers")
                    else:
                        logger.debug(f"HTTP error {e.response.status_code} for {url}")
                    rejections["http_error"] += 1
                    continue
                except Exception as e:
                    logger.debug(f"Error fetching article {url}: {e}")
                    rejections["other"] += 1
                    continue
            
            # Log summary with rejection reasons
            total_rejected = sum(rejections.values())
            if total_rejected > 0:
                rejection_summary = ", ".join([f"{count} {reason}" for reason, count in rejections.items() if count > 0])
                logger.info(f"✓ Successfully fetched {len(articles)} NEW articles from {source_name} (rejected {total_rejected}: {rejection_summary})")
            else:
                logger.info(f"✓ Successfully fetched {len(articles)} NEW articles from {source_name}")
            
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 403:
            logger.error(f"403 Forbidden for {source_name} homepage - site is blocking scrapers")
        else:
            logger.error(f"HTTP error fetching {source_name}: {e}")
    except Exception as e:
        logger.error(f"Error fetching articles from {source_name}: {e}", exc_info=True)
    
    return articles


async def scrape_all_sources(
    max_articles_per_source: int = 20,
    existing_urls: Optional[Set[str]] = None
) -> List[Dict]:
    """Scrape articles from all approved sources concurrently
    
    Args:
        max_articles_per_source: Maximum NEW articles to fetch per source
        existing_urls: Set of URLs already in database (to skip duplicates)
        
    Returns:
        List of all scraped articles
    """
    existing_urls = existing_urls or set()
    
    logger.info(f"Scraping all sources (max {max_articles_per_source} new articles per source)")
    logger.info(f"Skipping {len(existing_urls)} existing URLs")
    
    # Scrape each source concurrently
    tasks = []
    for domain in APPROVED_SOURCES.keys():
        task = fetch_articles_from_source(domain, max_articles_per_source, existing_urls)
        tasks.append(task)
    
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    all_articles = []
    for result in results:
        if isinstance(result, Exception):
            logger.error(f"Error scraping source: {result}")
            continue
        all_articles.extend(result)
    
    logger.info(f"✓ Scraped total of {len(all_articles)} NEW articles from all sources")
    
    return all_articles
