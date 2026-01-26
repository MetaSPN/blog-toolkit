"""Unified collector interface for feeds and crawler."""

import logging
from datetime import datetime
from typing import List, Optional, Tuple

from blog_toolkit.content_cleaner import clean_html, is_html
from blog_toolkit.crawler import BlogCrawler
from blog_toolkit.database import Database
from blog_toolkit.feeds import FeedParser
from blog_toolkit.config import Config

logger = logging.getLogger(__name__)


class BlogCollector:
    """Unified interface for collecting blog posts via RSS feeds or web crawler."""
    
    def __init__(self, db: Optional[Database] = None):
        """Initialize collector."""
        self.db = db or Database()
        self.feed_parser = FeedParser()
        self.crawler = BlogCrawler()
    
    def collect_blog(
        self,
        blog_url: str,
        method: str = "auto",
        author_name: Optional[str] = None,
        blog_name: Optional[str] = None,
    ) -> Optional[int]:
        """
        Collect posts from a blog.
        
        Args:
            blog_url: URL of the blog
            method: Collection method ('auto', 'rss', 'crawler')
            author_name: Name of the author (optional)
            blog_name: Name of the blog (optional)
        
        Returns:
            Blog ID if successful, None otherwise
        """
        logger.info(f"Collecting blog: {blog_url} (method: {method})")
        
        # Determine collection method
        if method == "auto":
            method = self._detect_best_method(blog_url)
        
        # Extract blog name if not provided
        if not blog_name:
            blog_name = self._extract_blog_name(blog_url)
        
        # Try to collect posts
        posts = []
        feed_url = None
        
        if method == "rss":
            feed_url, posts = self._collect_via_rss(blog_url, supplement_with_crawler=True)
        elif method == "crawler":
            posts = self._collect_via_crawler(blog_url)
        else:
            # Try RSS first, supplement with crawler if limited, fall back to crawler if RSS fails
            feed_url, posts = self._collect_via_rss(blog_url, supplement_with_crawler=True)
            if not posts:
                logger.info(f"RSS collection failed, trying crawler for {blog_url}")
                posts = self._collect_via_crawler(blog_url)
                method = "crawler"
        
        if not posts:
            logger.error(f"Failed to collect any posts from {blog_url}")
            return None
        
        # Create or update blog in database
        blog = self._get_or_create_blog(blog_url, blog_name, feed_url, author_name, method)
        
        # Add posts to database
        added_count = 0
        for post_data in posts:
            try:
                # Clean HTML content if present
                content = post_data.get("content")
                if content and is_html(content):
                    content = clean_html(content, preserve_structure=True)
                    logger.debug(f"Cleaned HTML from post: {post_data.get('title', 'Unknown')[:50]}")
                
                # Calculate word count and reading time from cleaned content
                word_count = None
                reading_time = None
                if content:
                    word_count = len(content.split())
                    # Average reading speed: 200 words per minute
                    reading_time = max(1, word_count // 200)
                
                self.db.add_post(
                    blog_id=blog.id,
                    title=post_data["title"],
                    url=post_data["url"],
                    content=content,
                    published_date=post_data.get("published_date"),
                    author=post_data.get("author") or author_name,
                    word_count=word_count,
                    reading_time=reading_time,
                    tags=post_data.get("tags", []),
                    categories=post_data.get("categories", []),
                    metadata=post_data.get("metadata", {}),
                )
                added_count += 1
            except Exception as e:
                logger.error(f"Error adding post {post_data.get('url')}: {e}")
        
        # Update collection time
        self.db.update_blog_collection_time(blog.id)
        
        logger.info(f"Successfully collected {added_count} posts from {blog_url}")
        return blog.id
    
    def update_blog(self, blog_id: int) -> int:
        """
        Update an existing blog by collecting new posts.
        
        Returns:
            Number of new posts added
        """
        blog = self.db.get_blog(blog_id)
        if not blog:
            raise ValueError(f"Blog with ID {blog_id} not found")
        
        logger.info(f"Updating blog: {blog.name} ({blog.url})")
        
        # Collect posts based on blog's collection method
        posts = []
        if blog.collection_method == "rss" and blog.feed_url:
            _, posts = self._collect_via_rss(blog.feed_url)
        else:
            posts = self._collect_via_crawler(blog.url)
        
        # Get existing post URLs to avoid duplicates
        existing_posts = self.db.get_posts_by_blog(blog_id)
        existing_urls = {post.url for post in existing_posts}
        
        # Add only new posts
        added_count = 0
        for post_data in posts:
            if post_data["url"] in existing_urls:
                continue
            
            try:
                # Clean HTML content if present
                content = post_data.get("content")
                if content and is_html(content):
                    content = clean_html(content, preserve_structure=True)
                    logger.debug(f"Cleaned HTML from post: {post_data.get('title', 'Unknown')[:50]}")
                
                # Calculate word count and reading time from cleaned content
                word_count = None
                reading_time = None
                if content:
                    word_count = len(content.split())
                    reading_time = max(1, word_count // 200)
                
                self.db.add_post(
                    blog_id=blog.id,
                    title=post_data["title"],
                    url=post_data["url"],
                    content=content,
                    published_date=post_data.get("published_date"),
                    author=post_data.get("author") or blog.author_name,
                    word_count=word_count,
                    reading_time=reading_time,
                    tags=post_data.get("tags", []),
                    categories=post_data.get("categories", []),
                    metadata=post_data.get("metadata", {}),
                )
                added_count += 1
            except Exception as e:
                logger.error(f"Error adding post {post_data.get('url')}: {e}")
        
        # Update collection time
        self.db.update_blog_collection_time(blog.id)
        
        logger.info(f"Added {added_count} new posts to blog {blog.name}")
        return added_count
    
    def _detect_best_method(self, blog_url: str) -> str:
        """Detect the best collection method for a blog."""
        # Try to discover RSS feed
        feed_url = self.feed_parser.discover_feed_url(blog_url)
        if feed_url:
            return "rss"
        return "crawler"
    
    def _collect_via_rss(self, feed_url_or_blog_url: str, supplement_with_crawler: bool = True) -> Tuple[Optional[str], List[dict]]:
        """
        Collect posts via RSS feed.
        
        Args:
            feed_url_or_blog_url: Feed URL or blog URL
            supplement_with_crawler: If True, use crawler to supplement if RSS seems limited
        
        Returns:
            Tuple of (feed_url, list of posts)
        """
        # If it's a blog URL, try to discover feed
        feed_url = feed_url_or_blog_url
        blog_url = None
        if not feed_url.endswith((".xml", ".rss", ".atom", "/feed", "/rss")):
            blog_url = feed_url_or_blog_url
            discovered = self.feed_parser.discover_feed_url(feed_url_or_blog_url)
            if discovered:
                feed_url = discovered
            else:
                return None, []
        
        feed_data = self.feed_parser.parse_feed(feed_url)
        if not feed_data:
            return feed_url, []
        
        entries = feed_data.get("entries", [])
        rss_count = len(entries)
        
        # Always do a quick check to see if there are more posts than RSS returned
        # This handles Ghost (15), Substack (20), and other limits
        is_substack = "substack.com" in (blog_url or feed_url_or_blog_url).lower()
        
        # For Substack with agent-browser available, always do full browser crawl
        # since we know it uses JS rendering and RSS is limited
        if supplement_with_crawler and rss_count > 0:
            # Determine blog URL from feed URL if not provided
            if not blog_url:
                blog_url = feed_data.get("link") or feed_url.replace("/rss/", "/").replace("/feed", "/").replace("/rss", "/").rstrip("/")
            
            if blog_url:
                if is_substack and self.crawler._agent_browser_path:
                    # For Substack, skip quick check and go straight to full browser crawl
                    logger.info(f"RSS feed returned {rss_count} posts. Substack detected with agent-browser - performing full browser crawl...")
                    crawled_posts = self.crawler.crawl_substack_with_browser(blog_url, max_posts=200)
                else:
                    # For other sites, do quick check first
                    logger.info(f"RSS feed returned {rss_count} posts. Quick-checking if more posts are available...")
                    has_more, quick_count = self.crawler.quick_crawl_check(blog_url, rss_count, max_pages_to_check=3)
                    
                    if has_more:
                        logger.info(f"Quick check found {quick_count} posts (RSS had {rss_count}). Performing full crawl...")
                        crawled_posts = self.crawler.crawl_blog(blog_url, max_posts=200)
                    else:
                        logger.info(f"Quick check confirms RSS feed is complete ({rss_count} posts found)")
                        crawled_posts = []
                
                # Merge crawled posts, avoiding duplicates
                if crawled_posts:
                    rss_urls = {entry["url"] for entry in entries}
                    new_posts = []
                    for crawled_post in crawled_posts:
                        if crawled_post.get("url") and crawled_post["url"] not in rss_urls:
                            new_posts.append(crawled_post)
                            rss_urls.add(crawled_post["url"])
                    
                    entries.extend(new_posts)
                    logger.info(f"Total posts after supplementing: {len(entries)} (added {len(new_posts)} from crawler)")
        
        return feed_url, entries
    
    def _collect_via_crawler(self, blog_url: str) -> List[dict]:
        """Collect posts via web crawler."""
        return self.crawler.crawl_blog(blog_url)
    
    def _extract_blog_name(self, blog_url: str) -> str:
        """Extract blog name from URL."""
        from urllib.parse import urlparse
        parsed = urlparse(blog_url)
        domain = parsed.netloc or parsed.path
        # Remove www. and common TLDs for cleaner name
        name = domain.replace("www.", "").split(".")[0]
        return name.capitalize()
    
    def _get_or_create_blog(
        self,
        blog_url: str,
        blog_name: str,
        feed_url: Optional[str],
        author_name: Optional[str],
        collection_method: str,
    ):
        """Get existing blog or create a new one."""
        # Check if blog already exists
        all_blogs = self.db.get_all_blogs()
        for blog in all_blogs:
            if blog.url == blog_url:
                # Update feed URL if we discovered one
                if feed_url and not blog.feed_url:
                    session = self.db.get_session()
                    try:
                        blog.feed_url = feed_url
                        blog.collection_method = collection_method
                        if author_name:
                            blog.author_name = author_name
                        session.commit()
                    finally:
                        session.close()
                return blog
        
        # Create new blog
        return self.db.add_blog(
            name=blog_name,
            url=blog_url,
            feed_url=feed_url,
            author_name=author_name,
            collection_method=collection_method,
        )
