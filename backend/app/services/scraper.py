import httpx
from abc import ABC, abstractmethod
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from dateutil import parser as date_parser
import logging
import asyncio
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

class BaseScraper(ABC):
    """Abstract base class for news scrapers"""
    
    def __init__(self, timeout: int = 10, rate_limit: float = 1.0):
        self.timeout = timeout
        self.rate_limit = rate_limit
        self.client = None
    
    @property
    @abstractmethod
    def source_name(self) -> str:
        """Return the name of the news source"""
        pass
    
    @abstractmethod
    async def fetch_articles(self, max_articles: int = 20) -> List[Dict]:
        """Fetch articles from the source"""
        pass
    
    async def _fetch_content(self, url: str, html: Optional[str] = None) -> Optional[str]:
        """Fetch and return page content"""
        try:
            if html:
                return html
            if not self.client:
                # Use headers to avoid bot detection
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.9',
                    'Accept-Encoding': 'gzip, deflate, br',
                    'Connection': 'keep-alive',
                    'Upgrade-Insecure-Requests': '1',
                    'Sec-Fetch-Dest': 'document',
                    'Sec-Fetch-Mode': 'navigate',
                    'Sec-Fetch-Site': 'none',
                    'Cache-Control': 'max-age=0',
                }
                self.client = httpx.AsyncClient(timeout=self.timeout, headers=headers, follow_redirects=True)
            response = await self.client.get(url)
            response.raise_for_status()
            return response.text
        except Exception as e:
            logger.warning(f"Error fetching {url}: {e}")
            return None
    
    def _extract_article_content(self, soup: BeautifulSoup) -> str:
        """Extract article content from HTML in a source-agnostic way
        
        Args:
            soup: BeautifulSoup object of article page
            
        Returns:
            Extracted article content text
        """
        # Try to find the main article container
        article_container = None
        
        # Strategy 1: Look for div with 'prose' class (common for article bodies)
        article_container = soup.find('div', {'class': lambda x: x and any(
            keyword in ' '.join(x).lower() if isinstance(x, list) else keyword in x.lower() if isinstance(x, str) else False
            for keyword in ['prose', 'article-body', 'article-content', 'post-content', 'entry-content', 'story-body']
        )})
        
        # Strategy 2: Look for <article> tag
        if not article_container:
            article_container = soup.find('article')
        
        # Strategy 3: Look for main tag
        if not article_container:
            article_container = soup.find('main')
        
        # Strategy 4: Fall back to body
        if not article_container:
            article_container = soup.find('body')
        
        if not article_container:
            return ""
        
        # Extract all paragraphs from the container
        paragraphs = article_container.find_all('p')
        
        # Filter and clean paragraphs
        content_parts = []
        for p in paragraphs:
            text = p.get_text(strip=True)
            
            # Filter out junk:
            # - Too short (likely navigation, labels, etc.)
            # - Common noise patterns
            # - Newsletter/footer content
            if len(text) < 30:
                continue
            
            text_lower = text.lower()
            
            # Skip common noise
            if text_lower in ['advertisement', 'about us', 'copy link', 'share', 'subscribe']:
                continue
            
            # Skip newsletter signup text
            if 'newsletter' in text_lower or 'subscribe' in text_lower or 'unsubscribe' in text_lower:
                continue
            
            # Skip footer-like content
            if 'stored on filecoin' in text_lower or 'articles are stored' in text_lower:
                continue
            
            content_parts.append(text)
        
        # Join paragraphs with space
        content = ' '.join(content_parts)
        
        # Return full article content
        return content
    
    def _parse_date(self, date_str: str) -> datetime:
        """Parse date string to datetime object (UTC)"""
        try:
            if not date_str:
                return datetime.utcnow()
            
            # Handle relative dates like "2 hours ago"
            if "ago" in date_str.lower():
                parts = date_str.lower().split()
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
            
            # Try parsing as absolute date
            parsed = date_parser.parse(date_str, fuzzy=True)
            return parsed.replace(tzinfo=None)
        except Exception as e:
            logger.warning(f"Error parsing date '{date_str}': {e}")
            return datetime.utcnow()
    
    async def close(self):
        """Close HTTP client"""
        if self.client:
            await self.client.aclose()


class CoinTelegraphScraper(BaseScraper):
    """Scraper for CoinTelegraph crypto news"""
    
    @property
    def source_name(self) -> str:
        return "CoinTelegraph"
    
    async def fetch_articles(self, max_articles: int = 20) -> List[Dict]:
        """Fetch articles from CoinTelegraph"""
        articles = []
        try:
            url = "https://cointelegraph.com"
            html = await self._fetch_content(url)
            if not html:
                return articles
            
            soup = BeautifulSoup(html, 'html.parser')
            
            # Method 1: Try to find article links directly
            article_elements = soup.find_all('article', limit=max_articles * 2)
            
            if not article_elements:
                # Method 2: Look for links with news/article patterns
                article_elements = soup.find_all('a', href=lambda x: x and x.startswith('/news/'), limit=max_articles * 2)
            
            processed_urls = set()
            for element in article_elements:
                if len(articles) >= max_articles:
                    break
                    
                try:
                    # Extract URL
                    if element.name == 'article':
                        link = element.find('a')
                        href = link.get('href') if link else None
                        # Extract title from article
                        title_elem = element.find(['h2', 'h3']) or element.find('span', {'class': lambda x: x and 'title' in str(x).lower() if x else False})
                    else:
                        href = element.get('href')
                        # Extract title from link or its descendants
                        title_elem = element.find(['h2', 'h3', 'span']) or element
                    
                    if not href or href in processed_urls:
                        continue
                    processed_urls.add(href)
                    
                    if not href.startswith('http'):
                        href = 'https://cointelegraph.com' + href
                    
                    # Extract title
                    if title_elem:
                        title = title_elem.get_text(strip=True)
                    else:
                        title = element.get_text(strip=True)
                    
                    if not title or len(title) < 10:
                        continue
                    
                    # Skip homepage navigation links
                    if href == 'https://cointelegraph.com/news' or 'category' in href.lower():
                        continue
                    
                    # Fetch article content
                    content_html = await self._fetch_content(href)
                    if not content_html:
                        continue
                    
                    content_soup = BeautifulSoup(content_html, 'html.parser')
                    
                    # Extract content using source-agnostic method
                    content = self._extract_article_content(content_soup)
                    
                    if len(content) < 100:
                        continue
                    
                    # Extract published date
                    date_elem = content_soup.find('time') or content_soup.find('span', {'class': lambda x: x and 'publish' in str(x).lower() if x else False})
                    published_date = datetime.utcnow()
                    if date_elem:
                        date_text = date_elem.get('datetime') or date_elem.get_text(strip=True)
                        published_date = self._parse_date(date_text)
                    
                    articles.append({
                        "title": title,
                        "content": content,
                        "url": href,
                        "source": self.source_name,
                        "published_date": published_date,
                    })
                    
                    await asyncio.sleep(self.rate_limit)
                
                except Exception as e:
                    logger.debug(f"Error processing CoinTelegraph article: {e}")
                    continue
        
        except Exception as e:
            logger.error(f"Error scraping CoinTelegraph: {e}")
        
        return articles


class TheDefiantScraper(BaseScraper):
    """Scraper for The Defiant crypto news"""
    
    @property
    def source_name(self) -> str:
        return "TheDefiant"
    
    async def fetch_articles(self, max_articles: int = 20) -> List[Dict]:
        """Fetch articles from The Defiant"""
        articles = []
        try:
            url = "https://thedefiant.io"
            html = await self._fetch_content(url)
            if not html:
                return articles
            
            soup = BeautifulSoup(html, 'html.parser')
            
            # Find all h2/h3 headings (skip first "Featured Stories" heading)
            headings = soup.find_all(['h2', 'h3'])
            
            processed_urls = set()  # Avoid duplicates
            
            for heading in headings:
                if len(articles) >= max_articles:
                    break
                    
                try:
                    title = heading.get_text(strip=True)
                    
                    # Skip generic/navigation headings
                    if not title or len(title) < 10 or title in ['Featured Stories', 'Latest News']:
                        continue
                    
                    # Look for link in parent hierarchy
                    href = None
                    current = heading.parent
                    depth = 0
                    while current and depth < 5:
                        # Check if current element has a link child to an article
                        link = current.find('a', href=lambda x: x and '/news/' in x)
                        if link:
                            href = link.get('href')
                            break
                        current = current.parent
                        depth += 1
                    
                    if not href or href in processed_urls:
                        continue
                    
                    processed_urls.add(href)
                    
                    if not href.startswith('http'):
                        href = 'https://thedefiant.io' + href
                    
                    # Fetch article content
                    content_html = await self._fetch_content(href)
                    if not content_html:
                        continue
                    
                    content_soup = BeautifulSoup(content_html, 'html.parser')
                    
                    # Extract content using source-agnostic method
                    content = self._extract_article_content(content_soup)
                    
                    if len(content) < 100:
                        continue
                    
                    # Extract published date
                    date_elem = content_soup.find('time') or content_soup.find('span', {'class': lambda x: x and 'date' in x.lower()})
                    published_date = datetime.utcnow()
                    if date_elem:
                        date_text = date_elem.get('datetime') or date_elem.get_text(strip=True)
                        published_date = self._parse_date(date_text)
                    
                    articles.append({
                        "title": title,
                        "content": content,
                        "url": href,
                        "source": self.source_name,
                        "published_date": published_date,
                    })
                    
                    await asyncio.sleep(self.rate_limit)
                
                except Exception as e:
                    logger.debug(f"Error processing The Defiant article: {e}")
                    continue
        
        except Exception as e:
            logger.error(f"Error scraping The Defiant: {e}")
        
        return articles


class DecryptScraper(BaseScraper):
    """Scraper for Decrypt crypto news"""
    
    @property
    def source_name(self) -> str:
        return "Decrypt"
    
    async def fetch_articles(self, max_articles: int = 20) -> List[Dict]:
        """Fetch articles from Decrypt"""
        articles = []
        try:
            url = "https://decrypt.co"
            html = await self._fetch_content(url)
            if not html:
                return articles
            
            soup = BeautifulSoup(html, 'html.parser')
            
            # Decrypt uses Next.js and embeds article data in __NEXT_DATA__ script tag
            article_urls = []
            
            # Method 1: Extract from __NEXT_DATA__ JSON
            script_tag = soup.find('script', id='__NEXT_DATA__')
            if script_tag:
                import json
                try:
                    data = json.loads(script_tag.string)
                    # Navigate to the articles in the JSON structure
                    if 'props' in data and 'pageProps' in data['props']:
                        article_previews = data['props']['pageProps'].get('dehydratedState', {}).get('queries', [])
                        for query in article_previews:
                            if 'state' in query and 'data' in query['state']:
                                articles_data = query['state']['data'].get('articles', {}).get('data', [])
                                for article in articles_data[:max_articles]:
                                    if 'slug' in article and 'id' in article:
                                        article_urls.append(f"/{article['id']}/{article['slug']}/")
                except Exception as e:
                    logger.debug(f"Error parsing __NEXT_DATA__: {e}")
            
            # Method 2: Look for links with article patterns
            if not article_urls:
                links = soup.find_all('a', href=lambda x: x and x.startswith('/') and not x.startswith('/price/'), limit=max_articles * 10)
                for link in links:
                    href = link.get('href', '')
                    # Filter for article URLs - should have numeric ID and slug
                    # Format: /123456/slug-text/
                    if '/' in href and href.startswith('/') and not href.startswith('/price/'):
                        # Check if it's not a category/section page (like /news/, /learn/, etc.)
                        parts = href.strip('/').split('/')
                        # Article URLs have format: id/slug (e.g., "346104/ethereum-network-megaeth...")
                        if len(parts) >= 2 and parts[0].isdigit() and len(parts[1]) > 5:
                            article_urls.append(href)
            
            # Remove duplicates while preserving order
            seen = set()
            unique_urls = []
            for url_path in article_urls:
                if url_path not in seen:
                    seen.add(url_path)
                    unique_urls.append(url_path)
            
            processed_urls = set()
            for url_path in unique_urls[:max_articles]:
                if len(articles) >= max_articles:
                    break
                    
                try:
                    # Construct full URL
                    if not url_path.startswith('http'):
                        href = 'https://decrypt.co' + url_path
                    else:
                        href = url_path
                    
                    if href in processed_urls:
                        continue
                    processed_urls.add(href)
                    
                    # Fetch article content
                    content_html = await self._fetch_content(href)
                    if not content_html:
                        continue
                    
                    content_soup = BeautifulSoup(content_html, 'html.parser')
                    
                    # Extract title
                    title_elem = content_soup.find('h1') or content_soup.find('title')
                    if not title_elem:
                        continue
                    title = title_elem.get_text(strip=True)
                    
                    # Skip if looks like a price page
                    if 'price' in url_path.lower():
                        continue
                    
                    # Extract content using source-agnostic method
                    content = self._extract_article_content(content_soup)
                    
                    if len(content) < 100:
                        continue
                    
                    # Extract published date
                    date_elem = content_soup.find('time') or content_soup.find('span', {'class': lambda x: x and 'date' in x.lower() if x else False})
                    published_date = datetime.utcnow()
                    if date_elem:
                        date_text = date_elem.get('datetime') or date_elem.get_text(strip=True)
                        published_date = self._parse_date(date_text)
                    
                    articles.append({
                        "title": title,
                        "content": content,
                        "url": href,
                        "source": self.source_name,
                        "published_date": published_date,
                    })
                    
                    await asyncio.sleep(self.rate_limit)
                
                except Exception as e:
                    logger.debug(f"Error processing Decrypt article: {e}")
                    continue
        
        except Exception as e:
            logger.error(f"Error scraping Decrypt: {e}")
        
        return articles


async def scrape_all_sources(max_articles: int = 20) -> List[Dict]:
    """Scrape articles from all sources concurrently"""
    scrapers = [
        CoinTelegraphScraper(),
        TheDefiantScraper(),
        DecryptScraper(),
    ]
    
    try:
        results = await asyncio.gather(*[
            scraper.fetch_articles(max_articles) 
            for scraper in scrapers
        ])
        
        all_articles = []
        for articles in results:
            all_articles.extend(articles)
        
        return all_articles
    
    finally:
        # Close all HTTP clients
        for scraper in scrapers:
            await scraper.close()
