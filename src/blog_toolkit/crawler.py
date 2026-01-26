"""Web crawler for blog posts."""

import json
import logging
import subprocess
import time
from datetime import datetime
from typing import List, Optional, Set
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from dateutil import parser as date_parser

from blog_toolkit.config import Config

logger = logging.getLogger(__name__)


class BlogCrawler:
    """Crawler for extracting blog posts from websites."""
    
    # Common blog post selectors for different CMS platforms
    POST_SELECTORS = {
        "wordpress": {
            "container": "article, .post, .entry, [class*='post']",
            "title": "h1.entry-title, h1.post-title, .entry-header h1, article h1",
            "content": ".entry-content, .post-content, .article-content, article .content",
            "date": "time.published, .published-date, .post-date, time[datetime]",
            "author": ".author, .by-author, .post-author, [rel='author']",
            "tags": ".tags a, .post-tags a, .entry-tags a",
            "categories": ".categories a, .post-categories a, .entry-categories a",
        },
        "medium": {
            "container": "article",
            "title": "h1, h2",
            "content": "[data-testid='post-content'], .postArticle-content",
            "date": "time, [data-testid='storyPublishDate']",
            "author": "[data-testid='authorName'], .author",
            "tags": ".tags a, [data-testid='tag']",
            "categories": None,
        },
        "substack": {
            "container": "article, .post, [class*='post-preview'], [class*='post-item'], a[href*='/p/']",
            "title": "h1.post-title, h1, h2, h3, [class*='title'], [class*='headline']",
            "content": ".post-content, .body, [class*='preview'], [class*='excerpt']",
            "date": "time, .publish-date, [class*='date'], [class*='published']",
            "author": ".author, .byline, [class*='author']",
            "tags": ".tags a, [class*='tag'] a",
            "categories": None,
        },
        "ghost": {
            "container": "article.post",
            "title": "h1.post-title",
            "content": ".post-content",
            "date": "time.published-date",
            "author": ".author",
            "tags": ".post-tags a",
            "categories": None,
        },
        "generic": {
            "container": "article, .post, .entry, [class*='post'], [class*='article']",
            "title": "h1, h2",
            "content": ".content, .post-content, .entry-content, main",
            "date": "time, .date, .published, [class*='date']",
            "author": ".author, [rel='author'], [class*='author']",
            "tags": ".tags a, [class*='tag'] a",
            "categories": ".categories a, [class*='category'] a",
        },
    }
    
    def __init__(self):
        """Initialize crawler."""
        self.timeout = Config.REQUEST_TIMEOUT
        self.retries = Config.REQUEST_RETRIES
        self.delay = Config.REQUEST_DELAY
        self.max_depth = Config.CRAWLER_MAX_DEPTH
        self.visited_urls: Set[str] = set()
        self._agent_browser_path = self._find_agent_browser()
    
    def _find_agent_browser(self) -> Optional[str]:
        """Find agent-browser executable."""
        try:
            result = subprocess.run(
                ["which", "agent-browser"],
                capture_output=True,
                text=True,
                timeout=2,
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
        except Exception:
            pass
        return None
    
    def crawl_substack_with_browser(self, blog_url: str, max_posts: Optional[int] = None) -> List[dict]:
        """
        Crawl Substack blog using agent-browser to handle JavaScript rendering.
        
        Args:
            blog_url: Base URL of the Substack blog
            max_posts: Maximum number of posts to extract
        
        Returns:
            List of post dictionaries
        """
        if not self._agent_browser_path:
            logger.warning("agent-browser not found, falling back to regular crawler")
            return self.crawl_blog(blog_url, max_posts)
        
        posts = []
        blog_url = blog_url.rstrip("/")
        seen_urls = set()
        
        try:
            # Use agent-browser to get rendered page
            logger.info(f"Using agent-browser to crawl Substack: {blog_url}")
            
            # Try archive page first (Substack often has better post listing there)
            archive_url = f"{blog_url}/archive"
            
            # Open the archive page if it exists, otherwise use main page
            result = subprocess.run(
                [self._agent_browser_path, "open", archive_url],
                capture_output=True,
                timeout=30,
            )
            
            # If archive page doesn't work, try main page
            if result.returncode != 0:
                subprocess.run(
                    [self._agent_browser_path, "open", blog_url],
                    capture_output=True,
                    timeout=30,
                )
            
            # Wait for page to load
            time.sleep(3)
            
            # Dismiss any modals/popups
            try:
                # Try to click "No thanks" or close button
                subprocess.run(
                    [self._agent_browser_path, "find", "text", "No thanks", "click"],
                    capture_output=True,
                    timeout=5,
                )
                time.sleep(1)
            except:
                pass
            
            # Use JavaScript to extract post links from the DOM
            # More comprehensive search for Substack post links
            js_code = """
            (function() {
                const allLinks = Array.from(document.querySelectorAll('a[href*="/p/"]'));
                const seenUrls = new Set();
                const posts = [];
                
                allLinks.forEach(link => {
                    const href = link.href || link.getAttribute('href');
                    if (href && href.includes('/p/') && !seenUrls.has(href)) {
                        seenUrls.add(href);
                        let title = link.textContent.trim();
                        if (!title || title.length < 3) {
                            // Try to find title in nearby elements
                            const parent = link.closest('article, [class*="post"], [class*="Post"]');
                            if (parent) {
                                const titleElem = parent.querySelector('h1, h2, h3, h4, h5, [class*="title"], [class*="Title"]');
                                if (titleElem) title = titleElem.textContent.trim();
                            }
                        }
                        posts.push({
                            url: href,
                            title: title || 'Untitled'
                        });
                    }
                });
                return posts;
            })();
            """
            
            result = subprocess.run(
                [self._agent_browser_path, "eval", js_code, "--json"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            
            logger.debug(f"agent-browser eval output: {result.stdout[:500]}")
            
            if result.returncode == 0:
                try:
                    # Parse the JSON output - agent-browser might wrap it
                    output = result.stdout.strip()
                    
                    # Try to parse as JSON directly first
                    try:
                        data = json.loads(output)
                        # If it's wrapped in a response object
                        if isinstance(data, dict) and "data" in data:
                            data_obj = data["data"]
                            # Check if there's a "result" key (agent-browser format)
                            if isinstance(data_obj, dict) and "result" in data_obj:
                                post_links = data_obj["result"]
                            elif isinstance(data_obj, list):
                                post_links = data_obj
                            else:
                                post_links = []
                        elif isinstance(data, list):
                            post_links = data
                        else:
                            post_links = []
                    except json.JSONDecodeError:
                        # Try to extract JSON from the output
                        output_lines = output.split('\n')
                        json_line = None
                        for line in output_lines:
                            stripped = line.strip()
                            if (stripped.startswith('{') or stripped.startswith('[')) and ('url' in stripped or 'title' in stripped):
                                json_line = stripped
                                break
                        
                        if json_line:
                            post_links = json.loads(json_line)
                        else:
                            # Last resort: try to find JSON in the output
                            import re
                            json_match = re.search(r'\[.*\]', output, re.DOTALL)
                            if json_match:
                                post_links = json.loads(json_match.group())
                            else:
                                post_links = []
                    
                    # Ensure post_links is a list
                    if not isinstance(post_links, list):
                        post_links = []
                    
                    logger.debug(f"Found {len(post_links)} post links from JavaScript")
                    
                    for item in post_links:
                        if isinstance(item, dict):
                            url = item.get("url", "")
                            if url and "/p/" in url and url not in seen_urls:
                                seen_urls.add(url)
                                posts.append({
                                    "title": item.get("title", "Untitled"),
                                    "url": url,
                                    "content": None,
                                    "published_date": None,
                                    "author": None,
                                    "tags": [],
                                    "categories": [],
                                    "metadata": {},
                                })
                                
                                if max_posts and len(posts) >= max_posts:
                                    break
                    
                    # Scroll and get more posts if needed
                    # Substack uses lazy loading, so we need to scroll and wait
                    if not max_posts or len(posts) < max_posts:
                        previous_count = len(posts)
                        no_change_count = 0
                        
                        for scroll_num in range(15):  # Scroll more times for Substack
                            subprocess.run(
                                [self._agent_browser_path, "scroll", "down", "3000"],
                                capture_output=True,
                                timeout=10,
                            )
                            time.sleep(3)  # Wait longer for lazy loading to complete
                            
                            # Get updated links
                            result = subprocess.run(
                                [self._agent_browser_path, "eval", js_code, "--json"],
                                capture_output=True,
                                text=True,
                                timeout=30,
                            )
                            
                            if result.returncode == 0:
                                try:
                                    output = result.stdout.strip()
                                    try:
                                        data = json.loads(output)
                                        if isinstance(data, dict) and "data" in data:
                                            data_obj = data["data"]
                                            if isinstance(data_obj, dict) and "result" in data_obj:
                                                post_links = data_obj["result"]
                                            elif isinstance(data_obj, list):
                                                post_links = data_obj
                                            else:
                                                post_links = []
                                        elif isinstance(data, list):
                                            post_links = data
                                        else:
                                            post_links = []
                                    except json.JSONDecodeError:
                                        output_lines = output.split('\n')
                                        json_line = None
                                        for line in output_lines:
                                            stripped = line.strip()
                                            if (stripped.startswith('{') or stripped.startswith('[')) and ('url' in stripped or 'title' in stripped):
                                                json_line = stripped
                                                break
                                        
                                        if json_line:
                                            post_links = json.loads(json_line)
                                        else:
                                            import re
                                            json_match = re.search(r'\[.*\]', output, re.DOTALL)
                                            if json_match:
                                                post_links = json.loads(json_match.group())
                                            else:
                                                post_links = []
                                    
                                    if not isinstance(post_links, list):
                                        post_links = []
                                    
                                    for item in post_links:
                                        if isinstance(item, dict):
                                            url = item.get("url", "")
                                            if url and "/p/" in url and url not in seen_urls:
                                                seen_urls.add(url)
                                                posts.append({
                                                    "title": item.get("title", "Untitled"),
                                                    "url": url,
                                                    "content": None,
                                                    "published_date": None,
                                                    "author": None,
                                                    "tags": [],
                                                    "categories": [],
                                                    "metadata": {},
                                                })
                                                
                                                if max_posts and len(posts) >= max_posts:
                                                    break
                                except Exception as e:
                                    logger.debug(f"Error parsing scroll results: {e}")
                            
                            if max_posts and len(posts) >= max_posts:
                                break
                    
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse agent-browser eval JSON: {e}")
                    logger.debug(f"Output was: {result.stdout[:500]}")
                except Exception as e:
                    logger.error(f"Error parsing agent-browser results: {e}")
            
            # Close browser (ensure it's closed even if there was an error)
            try:
                subprocess.run(
                    [self._agent_browser_path, "close"],
                    capture_output=True,
                    timeout=10,
                )
            except:
                pass  # Ignore errors when closing
            
            logger.info(f"Crawled {len(posts)} Substack posts using agent-browser")
            
        except subprocess.TimeoutExpired:
            logger.error("agent-browser command timed out")
        except FileNotFoundError:
            logger.error("agent-browser not found in PATH")
        except Exception as e:
            logger.error(f"Error using agent-browser: {e}")
            # Fall back to regular crawler
            return self.crawl_blog(blog_url, max_posts)
        
        return posts
    
    def quick_crawl_check(self, blog_url: str, rss_post_count: int, max_pages_to_check: int = 3) -> tuple[bool, int]:
        """
        Quick check to see if there are more posts than RSS feed returned.
        
        Args:
            blog_url: Base URL of the blog
            rss_post_count: Number of posts from RSS feed
            max_pages_to_check: Maximum number of pages to check (default: 3)
        
        Returns:
            Tuple of (has_more_posts, total_posts_found)
        """
        # For Substack, use browser-based check
        # Since Substack uses JS rendering, if browser finds posts, we should do full crawl
        if "substack.com" in blog_url.lower() and self._agent_browser_path:
            try:
                # Quick check: just see if we can find any posts at all
                # If yes, it means browser is needed and RSS is limited
                posts = self.crawl_substack_with_browser(blog_url, max_posts=10)  # Just check first 10
                found_count = len(posts)
                # If browser found any posts, RSS is definitely limited (Substack limits to 20)
                has_more = found_count > 0  # Any posts found means we need full crawl
                logger.info(f"Quick browser check found {found_count} posts (RSS had {rss_post_count})")
                return has_more, found_count
            except Exception as e:
                logger.warning(f"Browser-based quick check failed: {e}, falling back to regular check")
        
        # Regular quick check for other sites
        self.visited_urls.clear()
        posts = []
        
        # Normalize blog URL
        blog_url = blog_url.rstrip("/")
        if blog_url.endswith("/rss") or blog_url.endswith("/feed"):
            blog_url = blog_url.replace("/rss", "").replace("/feed", "").rstrip("/")
        
        # Only check first few pages for speed
        urls_to_check = [blog_url]
        for page in range(2, max_pages_to_check + 1):
            urls_to_check.append(f"{blog_url}/page/{page}/")
        
        for url in urls_to_check:
            page_posts = self._extract_posts_from_page(url, blog_url)
            for post in page_posts:
                if post and post["url"] and post["url"] not in [p["url"] for p in posts if p.get("url")]:
                    posts.append(post)
            
            # If we already found more than RSS, we can stop early
            if len(posts) > rss_post_count:
                logger.info(f"Quick check found {len(posts)} posts (RSS had {rss_post_count}), more posts available")
                return True, len(posts)
        
        logger.info(f"Quick check found {len(posts)} posts (RSS had {rss_post_count})")
        return len(posts) > rss_post_count, len(posts)
    
    def crawl_blog(self, blog_url: str, max_posts: Optional[int] = None) -> List[dict]:
        """
        Crawl a blog and extract posts.
        
        Args:
            blog_url: Base URL of the blog
            max_posts: Maximum number of posts to extract (None for all)
        
        Returns:
            List of post dictionaries
        """
        # For Substack, use browser-based crawler
        if "substack.com" in blog_url.lower() and self._agent_browser_path:
            return self.crawl_substack_with_browser(blog_url, max_posts)
        
        self.visited_urls.clear()
        posts = []
        
        # Normalize blog URL (remove trailing slashes, ensure it's the base)
        blog_url = blog_url.rstrip("/")
        if blog_url.endswith("/rss") or blog_url.endswith("/feed"):
            # If we got a feed URL, convert to blog URL
            blog_url = blog_url.replace("/rss", "").replace("/feed", "").rstrip("/")
        
        # Start with the main blog URL
        urls_to_visit = [blog_url]
        archive_urls = self._find_archive_pages(blog_url)
        urls_to_visit.extend(archive_urls)
        
        # Also try pagination patterns
        page = 2
        while page <= 10:  # Try up to 10 pages
            paginated_url = f"{blog_url}/page/{page}/"
            urls_to_visit.append(paginated_url)
            page += 1
        
        for url in urls_to_visit:
            if max_posts and len(posts) >= max_posts:
                break
            
            page_posts = self._extract_posts_from_page(url, blog_url)
            for post in page_posts:
                if post and post["url"] and post["url"] not in [p["url"] for p in posts if p.get("url")]:
                    posts.append(post)
                    if max_posts and len(posts) >= max_posts:
                        break
            
            time.sleep(self.delay)
        
        logger.info(f"Crawled {len(posts)} posts from {blog_url}")
        return posts
    
    def _find_archive_pages(self, blog_url: str) -> List[str]:
        """Find archive/index pages that list blog posts."""
        archive_urls = []
        
        try:
            response = requests.get(blog_url, timeout=self.timeout)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, "html.parser")
            
            # Look for common archive link patterns
            archive_patterns = [
                {"href": lambda x: x and ("archive" in x.lower() or "page" in x.lower())},
                {"class": lambda x: x and ("archive" in str(x).lower() or "pagination" in str(x).lower())},
            ]
            
            for pattern in archive_patterns:
                links = soup.find_all("a", pattern)
                for link in links[:5]:  # Limit to first 5 archive links
                    href = link.get("href")
                    if href:
                        full_url = urljoin(blog_url, href)
                        if full_url not in archive_urls:
                            archive_urls.append(full_url)
            
        except Exception as e:
            logger.error(f"Error finding archive pages for {blog_url}: {e}")
        
        return archive_urls
    
    def _extract_posts_from_page(self, page_url: str, base_url: str) -> List[dict]:
        """Extract posts from a single page."""
        if page_url in self.visited_urls:
            return []
        
        self.visited_urls.add(page_url)
        posts = []
        
        try:
            response = requests.get(page_url, timeout=self.timeout)
            # Handle 404s gracefully (pagination pages that don't exist)
            if response.status_code == 404:
                return []
            response.raise_for_status()
            soup = BeautifulSoup(response.content, "html.parser")
            
            # Special handling for Substack - look for /p/ links in the HTML
            # Substack uses JavaScript rendering, but post links are often in the HTML
            if "substack.com" in page_url.lower():
                # Find all links that look like post URLs
                post_links = soup.find_all("a", href=lambda x: x and "/p/" in x)
                seen_urls = set()
                for link in post_links:
                    href = link.get("href", "")
                    if href and "/p/" in href:
                        full_url = urljoin(base_url, href)
                        if full_url not in seen_urls:
                            seen_urls.add(full_url)
                            # Extract title from link text or nearby elements
                            title = link.get_text(strip=True)
                            if not title:
                                # Try to find title in parent or sibling
                                parent = link.parent
                                if parent:
                                    title_elem = parent.find(["h1", "h2", "h3", "h4"])
                                    if title_elem:
                                        title = title_elem.get_text(strip=True)
                            
                            posts.append({
                                "title": title or "Untitled",
                                "url": full_url,
                                "content": None,  # Will be fetched later if needed
                                "published_date": None,
                                "author": None,
                                "tags": [],
                                "categories": [],
                                "metadata": {},
                            })
                
                if posts:
                    logger.debug(f"Found {len(posts)} Substack posts via link pattern matching")
                    return posts
            
            # Try to detect CMS type
            cms_type = self._detect_cms(soup)
            selectors = self.POST_SELECTORS.get(cms_type, self.POST_SELECTORS["generic"])
            
            # Find post containers
            containers = soup.select(selectors["container"])
            
            for container in containers:
                post = self._extract_post_from_container(container, selectors, base_url)
                if post:
                    posts.append(post)
            
        except Exception as e:
            logger.error(f"Error extracting posts from {page_url}: {e}")
        
        return posts
    
    def _detect_cms(self, soup: BeautifulSoup) -> str:
        """Detect the CMS platform."""
        html_str = str(soup).lower()
        
        # Check URL first (most reliable)
        if hasattr(soup, 'url') or 'substack.com' in html_str:
            # Check for Substack-specific patterns
            if soup.find('div', class_=lambda x: x and 'post-preview' in x.lower()):
                return "substack"
            if soup.find('a', href=lambda x: x and '/p/' in x):
                return "substack"
        
        if "wp-content" in html_str or "wordpress" in html_str:
            return "wordpress"
        elif "medium.com" in html_str or "data-testid" in html_str:
            return "medium"
        elif "substack.com" in html_str or "substack" in html_str:
            return "substack"
        elif "ghost" in html_str:
            return "ghost"
        else:
            return "generic"
    
    def _extract_post_from_container(
        self, container: BeautifulSoup, selectors: dict, base_url: str
    ) -> Optional[dict]:
        """Extract post data from a container element."""
        try:
            # Extract URL first (most important)
            url = None
            link_elem = container.find("a", href=True)
            if link_elem:
                href = link_elem.get("href", "")
                if href:
                    url = urljoin(base_url, href)
            else:
                # Try to find URL in metadata or as container's href
                url = container.get("data-url") or container.get("href") or ""
                if url:
                    url = urljoin(base_url, url)
            
            # If container itself is a link (common in Substack)
            if not url and container.name == "a" and container.get("href"):
                url = urljoin(base_url, container["href"])
            
            if not url:
                return None  # Can't extract post without URL
            
            # Extract title
            title_elem = container.select_one(selectors["title"])
            if not title_elem:
                # Try finding title in link text
                if link_elem:
                    title_elem = link_elem
            title = title_elem.get_text(strip=True) if title_elem else "Untitled"
            
            # Extract content
            content_elem = container.select_one(selectors["content"])
            content = None
            if content_elem:
                # Get text content, removing script and style tags
                for script in content_elem(["script", "style"]):
                    script.decompose()
                content = content_elem.get_text(separator="\n", strip=True)
            
            # Extract published date
            date_elem = container.select_one(selectors["date"])
            published_date = None
            if date_elem:
                date_str = date_elem.get("datetime") or date_elem.get_text(strip=True)
                if date_str:
                    try:
                        published_date = date_parser.parse(date_str)
                    except (ValueError, TypeError):
                        pass
            
            # Extract author
            author_elem = container.select_one(selectors["author"])
            author = author_elem.get_text(strip=True) if author_elem else None
            
            # Extract tags
            tags = []
            tag_elems = container.select(selectors["tags"]) if selectors["tags"] else []
            for tag_elem in tag_elems:
                tag_text = tag_elem.get_text(strip=True)
                if tag_text:
                    tags.append(tag_text)
            
            # Extract categories
            categories = []
            if selectors["categories"]:
                cat_elems = container.select(selectors["categories"])
                for cat_elem in cat_elems:
                    cat_text = cat_elem.get_text(strip=True)
                    if cat_text:
                        categories.append(cat_text)
            
            return {
                "title": title,
                "url": url,
                "content": content,
                "published_date": published_date,
                "author": author,
                "tags": tags,
                "categories": categories,
                "metadata": {},
            }
            
        except Exception as e:
            logger.error(f"Error extracting post from container: {e}")
            return None
    
    def get_post_content(self, post_url: str) -> Optional[str]:
        """Get full content of a blog post from its URL."""
        try:
            response = requests.get(post_url, timeout=self.timeout)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, "html.parser")
            
            # Try to find main content area
            content_selectors = [
                "article",
                ".post-content",
                ".entry-content",
                ".article-content",
                "main",
                "[role='main']",
            ]
            
            for selector in content_selectors:
                content_elem = soup.select_one(selector)
                if content_elem:
                    # Remove script and style tags
                    for script in content_elem(["script", "style", "nav", "header", "footer"]):
                        script.decompose()
                    return content_elem.get_text(separator="\n", strip=True)
            
            # Fallback: get body text
            body = soup.find("body")
            if body:
                for script in body(["script", "style", "nav", "header", "footer"]):
                    script.decompose()
                return body.get_text(separator="\n", strip=True)
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting post content from {post_url}: {e}")
            return None
