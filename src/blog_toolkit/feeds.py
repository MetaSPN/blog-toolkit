"""RSS/Atom feed parser for blog-toolkit."""

import logging
import time
from datetime import datetime
from typing import List, Optional
from urllib.parse import urljoin, urlparse

import feedparser
import requests
from dateutil import parser as date_parser

from blog_toolkit.config import Config

logger = logging.getLogger(__name__)


class FeedParser:
    """Parser for RSS/Atom feeds."""
    
    def __init__(self):
        """Initialize feed parser."""
        self.timeout = Config.REQUEST_TIMEOUT
        self.retries = Config.REQUEST_RETRIES
        self.delay = Config.REQUEST_DELAY
    
    def parse_feed(self, feed_url: str, max_pages: int = 10) -> Optional[dict]:
        """
        Parse an RSS/Atom feed, including pagination if available.
        
        Args:
            feed_url: URL of the RSS/Atom feed
            max_pages: Maximum number of pages to fetch (default: 10)
        
        Returns:
            Dictionary with feed metadata and entries, or None if parsing fails.
        """
        all_entries = []
        feed_metadata = None
        
        # Try to parse paginated feeds
        page = 1
        while page <= max_pages:
            # Construct page URL
            if page == 1:
                current_url = feed_url
            else:
                # Try different pagination patterns
                base_url = feed_url.rstrip("/")
                pagination_patterns = [
                    f"{base_url}/page/{page}/",
                    f"{base_url}/{page}/",
                    f"{base_url}?page={page}",
                    f"{base_url}&page={page}",
                ]
                current_url = None
                for pattern in pagination_patterns:
                    try:
                        test_response = requests.head(pattern, timeout=5, allow_redirects=True)
                        if test_response.status_code == 200:
                            content_type = test_response.headers.get("content-type", "").lower()
                            if any(t in content_type for t in ["xml", "rss", "atom"]):
                                current_url = pattern
                                break
                    except:
                        continue
                
                if not current_url:
                    # No more pages available
                    break
            
            # Parse the current page
            page_data = self._parse_feed_page(current_url)
            if not page_data:
                break
            
            # Store metadata from first page
            if page == 1:
                feed_metadata = {
                    "title": page_data.get("title", "Untitled Feed"),
                    "link": page_data.get("link", ""),
                    "description": page_data.get("description", ""),
                    "author": page_data.get("author", ""),
                }
            
            # Add entries
            entries = page_data.get("entries", [])
            if not entries:
                break
            
            all_entries.extend(entries)
            
            # Check for pagination links in the feed
            has_next = self._check_for_next_page(page_data, feed_url)
            if not has_next:
                break
            
            page += 1
            time.sleep(self.delay)  # Be respectful with requests
        
        if not feed_metadata:
            return None
        
        feed_data = {
            **feed_metadata,
            "entries": all_entries,
        }
        
        logger.info(f"Parsed {len(all_entries)} entries from {feed_url} ({page} page(s))")
        return feed_data
    
    def _parse_feed_page(self, feed_url: str) -> Optional[dict]:
        """Parse a single page of an RSS/Atom feed."""
        for attempt in range(self.retries):
            try:
                # Parse the feed
                parsed = feedparser.parse(feed_url)
                
                if parsed.bozo and parsed.bozo_exception:
                    logger.warning(f"Feed parsing warning: {parsed.bozo_exception}")
                
                if not parsed.entries:
                    return None
                
                # Extract feed metadata
                feed_info = parsed.feed
                feed_data = {
                    "title": feed_info.get("title", "Untitled Feed"),
                    "link": feed_info.get("link", ""),
                    "description": feed_info.get("description", ""),
                    "author": feed_info.get("author", ""),
                    "entries": [],
                }
                
                # Parse entries
                for entry in parsed.entries:
                    entry_data = self._parse_entry(entry, feed_data["link"])
                    if entry_data:
                        feed_data["entries"].append(entry_data)
                
                return feed_data
                
            except Exception as e:
                logger.error(f"Error parsing feed {feed_url} (attempt {attempt + 1}/{self.retries}): {e}")
                if attempt < self.retries - 1:
                    time.sleep(self.delay * (attempt + 1))
                else:
                    return None
        
        return None
    
    def _check_for_next_page(self, feed_data: dict, base_url: str) -> bool:
        """Check if there's a next page available (by checking for pagination links)."""
        # This is a simple check - in practice, RSS feeds rarely have explicit pagination
        # Most feeds are limited to a certain number of items
        # We'll rely on trying pagination patterns instead
        return False  # Conservative: don't assume pagination exists
    
    def _parse_entry(self, entry: dict, base_url: str) -> Optional[dict]:
        """Parse a single feed entry."""
        try:
            # Extract title
            title = entry.get("title", "Untitled")
            
            # Extract URL
            link = entry.get("link", "")
            if not link and entry.get("links"):
                link = entry.links[0].get("href", "")
            
            # Make URL absolute if needed
            if link and not urlparse(link).netloc:
                link = urljoin(base_url, link)
            
            # Extract content
            content = None
            if entry.get("content"):
                # Try to get the first content item
                content_items = entry.content if isinstance(entry.content, list) else [entry.content]
                if content_items:
                    content = content_items[0].get("value", "")
            elif entry.get("summary"):
                content = entry.summary
            elif entry.get("description"):
                content = entry.description
            
            # Extract published date
            published_date = None
            for date_field in ["published", "published_parsed", "updated", "updated_parsed"]:
                if date_field in entry:
                    date_value = entry[date_field]
                    if isinstance(date_value, tuple):
                        # parsed date tuple
                        try:
                            published_date = datetime(*date_value[:6])
                        except (ValueError, TypeError):
                            pass
                    elif isinstance(date_value, str):
                        # date string
                        try:
                            published_date = date_parser.parse(date_value)
                        except (ValueError, TypeError):
                            pass
                    break
            
            # Extract author
            author = None
            if entry.get("author"):
                author = entry.author
            elif entry.get("authors") and len(entry.authors) > 0:
                author = entry.authors[0].get("name", "")
            
            # Extract tags
            tags = []
            if entry.get("tags"):
                tags = [tag.get("term", "") for tag in entry.tags if tag.get("term")]
            
            # Extract categories
            categories = []
            if entry.get("categories"):
                categories = [cat.get("term", "") for cat in entry.categories if cat.get("term")]
            
            return {
                "title": title,
                "url": link,
                "content": content,
                "published_date": published_date,
                "author": author,
                "tags": tags,
                "categories": categories,
                "metadata": {
                    "id": entry.get("id", link),
                    "summary": entry.get("summary", ""),
                },
            }
            
        except Exception as e:
            logger.error(f"Error parsing entry: {e}")
            return None
    
    def discover_feed_url(self, blog_url: str) -> Optional[str]:
        """
        Try to discover RSS/Atom feed URL from a blog URL.
        
        Returns:
            Feed URL if found, None otherwise.
        """
        try:
            response = requests.get(blog_url, timeout=self.timeout)
            response.raise_for_status()
            
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(response.content, "html.parser")
            
            # Look for common feed link patterns
            feed_patterns = [
                ('link', {'type': 'application/rss+xml'}),
                ('link', {'type': 'application/atom+xml'}),
                ('link', {'type': 'application/json'}),
                ('link', {'rel': 'alternate', 'type': 'application/rss+xml'}),
                ('link', {'rel': 'alternate', 'type': 'application/atom+xml'}),
            ]
            
            for tag_name, attrs in feed_patterns:
                links = soup.find_all(tag_name, attrs)
                if links:
                    href = links[0].get("href")
                    if href:
                        # Make absolute URL
                        return urljoin(blog_url, href)
            
            # Try common feed paths
            common_paths = [
                "/feed",
                "/feed.xml",
                "/rss",
                "/rss.xml",
                "/atom.xml",
                "/feeds/posts/default",
                "/index.xml",
            ]
            
            for path in common_paths:
                feed_url = urljoin(blog_url, path)
                try:
                    test_response = requests.head(feed_url, timeout=5, allow_redirects=True)
                    if test_response.status_code == 200:
                        content_type = test_response.headers.get("content-type", "").lower()
                        if any(t in content_type for t in ["xml", "rss", "atom", "json"]):
                            return feed_url
                except:
                    continue
            
            return None
            
        except Exception as e:
            logger.error(f"Error discovering feed for {blog_url}: {e}")
            return None
