import logging
import asyncio
import httpx
from typing import List, Dict, Optional, Set
from datetime import datetime, timedelta, timezone
from dateutil import parser as date_parser
from bs4 import BeautifulSoup
from urllib.parse import urlparse, urljoin

logger = logging.getLogger(__name__)

APPROVED_SOURCES = {
    "cointelegraph.com": "CoinTelegraph",
    "thedefiant.io": "TheDefiant",
    "dlnews.com": "DLNews",
}

SOURCE_HOMEPAGES = {
    "cointelegraph.com": "https://cointelegraph.com/category/latest-news",
    "thedefiant.io": "https://thedefiant.io/",
    "dlnews.com": "https://www.dlnews.com/articles/",
}

SOURCE_PATTERNS = {
    "cointelegraph.com": {
        "article_prefixes": ["/news/"],
        "excluded_prefixes": ["/magazine/", "/learn/", "/price-indexes/", "/people/", "/category/"],
        "min_path_segments": 2,
        "min_slug_length": 20,
    },
    "dlnews.com": {
        "article_prefixes": ["/articles/"],
        "min_path_segments": 3,
        "min_slug_length": 20,
    },
    "thedefiant.io": {
        "article_prefixes": ["/news/"],
        "excluded_prefixes": ["/podcasts-and-videos/"],
        "min_path_segments": 3,
        "min_slug_length": 20,
    },
}

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
    """Check if URL is from an approved source"""
    for domain in APPROVED_SOURCES.keys():
        if domain in url:
            return True
    return False


def get_domain(url: str) -> str:
    """Extract domain from URL"""
    parsed = urlparse(url)
    return parsed.netloc.replace('www.', '')


def looks_like_article(url: str, base_domain: str) -> bool:
    """Validate if URL is an article using site-specific patterns"""
    if base_domain not in url:
        return False
    
    if base_domain not in SOURCE_PATTERNS:
        logger.warning(f"No URL pattern configured for {base_domain}, using fallback validation")
        return _fallback_article_check(url)
    
    pattern = SOURCE_PATTERNS[base_domain]
    parsed = urlparse(url)
    path = parsed.path.strip('/')
    
    if not path:
        return False
    
    if "excluded_prefixes" in pattern:
        for excluded in pattern["excluded_prefixes"]:
            if path.startswith(excluded.lstrip('/')):
                logger.debug(f"URL excluded by prefix {excluded}: {url}")
                return False
    
    if "article_prefixes" in pattern:
        has_valid_prefix = any(
            path.startswith(prefix.lstrip('/'))
            for prefix in pattern["article_prefixes"]
        )
        if not has_valid_prefix:
            logger.debug(f"URL missing required prefix: {url}")
            return False
    
    path_segments = [seg for seg in path.split('/') if seg]
    min_segments = pattern.get("min_path_segments", 2)
    
    if len(path_segments) < min_segments:
        logger.debug(f"URL has {len(path_segments)} segments, need {min_segments}: {url}")
        return False
    
    last_segment = path_segments[-1]
    min_slug_length = pattern.get("min_slug_length", 15)
    
    if len(last_segment) < min_slug_length:
        logger.debug(f"URL slug too short ({len(last_segment)} < {min_slug_length}): {url}")
        return False
    
    return True


def _fallback_article_check(url: str) -> bool:
    """Fallback heuristic for sources without specific patterns"""
    parsed = urlparse(url)
    path = parsed.path.lower().strip('/')
    
    if not path:
        return False
    
    path_segments = [seg for seg in path.split('/') if seg]
    
    if len(path_segments) < 2:
        return False
    
    if len(path_segments[-1]) < 20:
        return False
    
    return True


def extract_article_content(soup: BeautifulSoup) -> str:
    """Extract article content from parsed HTML"""
    for element in soup.find_all(['nav', 'header', 'footer', 'script', 'style', 'aside', 'iframe', 'form']):
        element.decompose()
    
    noise_patterns = [
        'nav', 'menu', 'sidebar', 'advertisement', 'ad-', 'banner',
        'cookie', 'newsletter', 'subscribe', 'subscription',
        'social', 'share', 'comment', 'related', 'recommend',
        'footer', 'header', 'popup', 'modal', 'overlay'
    ]
    
    for pattern in noise_patterns:
        for element in soup.find_all(attrs={'class': lambda x: x and pattern in ' '.join(x).lower() if isinstance(x, list) else pattern in x.lower() if isinstance(x, str) else False}):
            element.decompose()
        for element in soup.find_all(attrs={'id': lambda x: x and pattern in x.lower() if isinstance(x, str) else False}):
            element.decompose()
    
    article_container = (
        soup.find('article') or
        soup.find('div', {'class': lambda x: x and any(
            keyword in ' '.join(x).lower() if isinstance(x, list) else keyword in x.lower() if isinstance(x, str) else False
            for keyword in ['article-body', 'article-content', 'post-content', 'entry-content', 'story-body', 'prose', 'content-body']
        )}) or
        soup.find('main') or
        soup.find('body')
    )
    
    if not article_container:
        return ""
    
    paragraphs = article_container.find_all('p')
    content_parts = []
    
    noise_keywords = [
        'advertisement', 'sponsored', 'subscribe', 'newsletter',
        'cookie policy', 'privacy policy', 'terms of service',
        'follow us', 'share this', 'sign up', 'sign in',
        'read more about', 'related articles', 'recommended for you',
        'stored on filecoin'
    ]
    
    for p in paragraphs:
        text = p.get_text(strip=True)
        
        if len(text) < 30:
            continue
        
        if any(keyword in text.lower() for keyword in noise_keywords):
            continue
        
        content_parts.append(text)
    
    return ' '.join(content_parts)


def extract_article_title(soup: BeautifulSoup) -> Optional[str]:
    """Extract article title"""
    title_elem = soup.find('h1')
    if title_elem:
        return title_elem.get_text(strip=True)
    
    meta_title = soup.find('meta', {'property': 'og:title'})
    if meta_title:
        return meta_title.get('content', '').strip()
    
    title_tag = soup.find('title')
    if title_tag:
        title = title_tag.get_text(strip=True)
        if '|' in title:
            title = title.split('|')[0].strip()
        if ' - ' in title:
            title = title.split(' - ')[0].strip()
        return title
    
    return None


def parse_article_date(soup: BeautifulSoup) -> datetime:
    """Extract article published date"""
    date_elem = soup.find('time')
    if date_elem and date_elem.get('datetime'):
        try:
            return date_parser.parse(date_elem.get('datetime')).replace(tzinfo=None)
        except:
            pass
    
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
    
    if date_elem:
        date_str = date_elem.get_text(strip=True)
        try:
            if "ago" in date_str.lower():
                parts = date_str.lower().split()
                try:
                    value = int(parts[0])
                    unit = parts[1]
                    
                    if "minute" in unit:
                        return datetime.now(timezone.utc) - timedelta(minutes=value)
                    elif "hour" in unit:
                        return datetime.now(timezone.utc) - timedelta(hours=value)
                    elif "day" in unit:
                        return datetime.now(timezone.utc) - timedelta(days=value)
                    elif "week" in unit:
                        return datetime.now(timezone.utc) - timedelta(weeks=value)
                    elif "month" in unit:
                        return datetime.now(timezone.utc) - timedelta(days=value*30)
                except:
                    pass
            
            return date_parser.parse(date_str, fuzzy=True).replace(tzinfo=None)
        except:
            pass
    
    return datetime.now(timezone.utc)


async def fetch_articles_from_source(
    domain: str,
    max_articles: int = 20,
    existing_urls: Optional[Set[str]] = None,
    rate_limit: float = 1.0
) -> List[Dict]:
    """Fetch articles from a single source"""
    if domain not in APPROVED_SOURCES:
        logger.warning(f"Source {domain} not in approved sources")
        return []
    
    source_name = APPROVED_SOURCES[domain]
    homepage = SOURCE_HOMEPAGES.get(domain, f"https://{domain}/")
    existing_urls = existing_urls or set()
    articles = []
    
    logger.info(f"Fetching articles from {source_name} ({homepage})")
    
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True, headers=DEFAULT_HEADERS) as client:
            response = await client.get(homepage)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            potential_article_links = []
            seen_urls = set()
            
            for link in soup.find_all('a', href=True):
                href = link.get('href')
                
                if href.startswith('//'):
                    href = 'https:' + href
                elif href.startswith('/'):
                    parsed_homepage = urlparse(homepage)
                    href = f"{parsed_homepage.scheme}://{parsed_homepage.netloc}{href}"
                elif not href.startswith('http'):
                    href = urljoin(homepage, href)
                
                href = href.split('#')[0].split('?')[0].rstrip('/')
                
                if href in seen_urls:
                    continue
                seen_urls.add(href)
                
                if not is_approved_source(href):
                    continue
                
                url_domain = get_domain(href)
                if url_domain != domain:
                    continue
                
                if href in existing_urls:
                    continue
                
                if looks_like_article(href, domain):
                    potential_article_links.append(href)
            
            logger.info(f"Found {len(potential_article_links)} potential NEW article links on {source_name} homepage")
            
            rejections = {"title": 0, "content": 0, "http_error": 0, "other": 0}
            
            for url in potential_article_links[:max_articles * 3]:
                if len(articles) >= max_articles:
                    break
                
                try:
                    await asyncio.sleep(rate_limit)
                    
                    article_response = await client.get(url)
                    article_response.raise_for_status()
                    
                    article_soup = BeautifulSoup(article_response.text, 'html.parser')
                    title = extract_article_title(article_soup)
                    
                    if not title or len(title) < 10:
                        rejections["title"] += 1
                        continue
                    
                    content = extract_article_content(article_soup)
                    
                    if len(content) < 100:
                        rejections["content"] += 1
                        continue
                    
                    published_date = parse_article_date(article_soup)
                    
                    articles.append({
                        "title": title,
                        "content": content,
                        "url": url,
                        "source": source_name,
                        "published_date": published_date,
                    })
                    
                except httpx.HTTPStatusError as e:
                    if e.response.status_code == 403:
                        logger.warning(f"403 Forbidden for {url} - site may be blocking scrapers")
                    rejections["http_error"] += 1
                    continue
                except Exception as e:
                    logger.debug(f"Error fetching article {url}: {e}")
                    rejections["other"] += 1
                    continue
            
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
    """Scrape articles from all approved sources concurrently"""
    existing_urls = existing_urls or set()
    
    logger.info(f"Scraping all sources (max {max_articles_per_source} new articles per source)")
    logger.info(f"Skipping {len(existing_urls)} existing URLs")
    
    tasks = [
        fetch_articles_from_source(domain, max_articles_per_source, existing_urls)
        for domain in APPROVED_SOURCES.keys()
    ]
    
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    all_articles = []
    for result in results:
        if isinstance(result, Exception):
            logger.error(f"Error scraping source: {result}")
            continue
        all_articles.extend(result)
    
    logger.info(f"✓ Scraped total of {len(all_articles)} NEW articles from all sources")
    
    return all_articles
