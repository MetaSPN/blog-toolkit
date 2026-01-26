"""MetaSPN content repository exporter."""

import json
import logging
import subprocess
import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Set
from urllib.parse import urlparse

from blog_toolkit.analyzer import BlogAnalyzer
from blog_toolkit.config import Config
from blog_toolkit.database import Database

logger = logging.getLogger(__name__)


class MetaSPNExporter:
    """Export blog posts to MetaSPN content repository format."""
    
    def __init__(self, db: Optional[Database] = None):
        """Initialize exporter."""
        self.db = db or Database()
        self.analyzer = BlogAnalyzer(self.db) if db else BlogAnalyzer()
        self.schema_version = Config.METASPN_SCHEMA_VERSION
    
    def initialize_repository(self, repo_path: str, user_id: str) -> Path:
        """
        Initialize MetaSPN repository structure.
        
        Args:
            repo_path: Path to repository directory
            user_id: MetaSPN user ID
        
        Returns:
            Path to repository root
        """
        repo = Path(repo_path)
        repo.mkdir(parents=True, exist_ok=True)
        
        # Create directory structure
        (repo / "artifacts" / "blog").mkdir(parents=True, exist_ok=True)
        (repo / "sources" / "blogs").mkdir(parents=True, exist_ok=True)
        (repo / "reports").mkdir(parents=True, exist_ok=True)
        (repo / "embeddings").mkdir(parents=True, exist_ok=True)
        
        # Create posts.jsonl if it doesn't exist
        posts_file = repo / "artifacts" / "blog" / "posts.jsonl"
        if not posts_file.exists():
            posts_file.touch()
        
        # Create reading-events.jsonl if it doesn't exist
        events_file = repo / "sources" / "blogs" / "reading-events.jsonl"
        if not events_file.exists():
            events_file.touch()
        
        # Initialize meta.json
        meta_file = repo / "meta.json"
        if not meta_file.exists():
            meta_data = {
                "schema_version": self.schema_version,
                "user_id": user_id,
                "last_sync": datetime.utcnow().isoformat() + "Z",
                "repositories": {
                    "blog": {
                        "last_export": None,
                        "total_posts": 0,
                    }
                }
            }
            with open(meta_file, "w") as f:
                json.dump(meta_data, f, indent=2)
        
        # Create .gitignore if it doesn't exist
        gitignore_file = repo / ".gitignore"
        if not gitignore_file.exists():
            gitignore_content = """# MetaSPN Content Repository
# Exclude sensitive data
*.env
*.key
*.pem

# Exclude large embeddings if needed
# embeddings/**/*.npy
"""
            with open(gitignore_file, "w") as f:
                f.write(gitignore_content)
        
        # Create README.md template if it doesn't exist
        readme_file = repo / "README.md"
        if not readme_file.exists():
            readme_content = f"""# MetaSPN Content Repository

This repository contains your content artifacts and consumption data for MetaSPN analysis.

## Structure

- `artifacts/blog/posts.jsonl` - Your blog posts
- `sources/blogs/reading-events.jsonl` - Blog reading events
- `reports/` - Generated analysis reports (updated by MetaSPN platform)
- `meta.json` - Repository metadata and sync information

## User ID

{user_id}

## Last Sync

{datetime.utcnow().isoformat()}Z

---
*This repository is managed by blog-toolkit*
"""
            with open(readme_file, "w") as f:
                f.write(readme_content)
        
        logger.info(f"Initialized MetaSPN repository at {repo}")
        return repo
    
    def export_posts(
        self,
        blog_ids: Optional[List[int]],
        repo_path: str,
        user_id: str,
        compute_analysis: bool = False,
    ) -> int:
        """
        Export blog posts to MetaSPN repository.
        
        Args:
            blog_ids: List of blog IDs to export (None for all)
            repo_path: Path to MetaSPN repository
            user_id: MetaSPN user ID
            compute_analysis: Whether to compute game signatures and analysis
        
        Returns:
            Number of posts exported
        """
        repo = Path(repo_path)
        
        # Initialize repository if needed (always ensure structure exists)
        self.initialize_repository(repo_path, user_id)
        
        # Get posts to export
        if blog_ids:
            all_posts = []
            for blog_id in blog_ids:
                posts = self.db.get_posts_by_blog(blog_id)
                all_posts.extend(posts)
        else:
            blogs = self.db.get_all_blogs()
            all_posts = []
            for blog in blogs:
                posts = self.db.get_posts_by_blog(blog.id)
                all_posts.extend(posts)
        
        if not all_posts:
            logger.warning("No posts found to export")
            return 0
        
        # Get existing post URLs to avoid duplicates
        posts_file = repo / "artifacts" / "blog" / "posts.jsonl"
        existing_urls = self._get_existing_post_urls(posts_file)
        
        # Convert and write posts
        exported_count = 0
        with open(posts_file, "a") as f:
            for post in all_posts:
                # Skip if already exported
                if post.url in existing_urls:
                    continue
                
                blog = self.db.get_blog(post.blog_id)
                if not blog:
                    continue
                
                # Convert to MetaSPN format
                metaspn_post = self.convert_post_to_metaspn(
                    post, blog, user_id, compute_analysis
                )
                
                # Write as JSONL (one JSON object per line)
                f.write(json.dumps(metaspn_post, default=str) + "\n")
                exported_count += 1
                existing_urls.add(post.url)
        
        # Update meta.json
        self.update_meta_json(repo_path, user_id, exported_count)
        
        logger.info(f"Exported {exported_count} posts to MetaSPN repository")
        return exported_count
    
    def convert_post_to_metaspn(
        self,
        post,
        blog,
        user_id: str,
        compute_analysis: bool = False,
    ) -> dict:
        """
        Convert a Post object to MetaSPN artifact format.
        
        Args:
            post: Post database object
            blog: Blog database object
            user_id: MetaSPN user ID
            compute_analysis: Whether to compute analysis fields
        
        Returns:
            Dictionary in MetaSPN format
        """
        # Generate UUID for post
        post_uuid = str(uuid.uuid4())
        
        # Extract slug from URL
        slug = self._extract_slug_from_url(post.url)
        
        # Get excerpt (first 300 characters)
        content = post.content or ""
        excerpt = content[:300] + "..." if len(content) > 300 else content
        
        # Base structure
        metaspn_post = {
            "id": post_uuid,
            "timestamp": (post.published_date or datetime.utcnow()).isoformat() + "Z",
            "user_id": user_id,
            "version": self.schema_version,
            "post": {
                "title": post.title,
                "url": post.url,
                "slug": slug,
                "publish_date": post.published_date.isoformat() + "Z" if post.published_date else None,
                "word_count": post.word_count,
                "categories": post.categories_list,
            },
            "content": {
                "plain_text": content,
                "excerpt": excerpt,
            },
            "metrics": {},  # Empty for now
            "references": {
                "citations": [],
                "influenced_by": [],
            },
        }
        
        # Add analysis if requested
        if compute_analysis:
            analysis = self._compute_post_analysis(post, blog)
            metaspn_post["analysis"] = analysis
        else:
            metaspn_post["analysis"] = {}
        
        return metaspn_post
    
    def _compute_post_analysis(self, post, blog) -> dict:
        """Compute analysis for a single post."""
        analysis = {
            "themes": post.tags_list + post.categories_list,
            "reading_level": self._estimate_reading_level(post.word_count or 0),
            "complexity_score": self._compute_complexity_score(post),
        }
        
        # Placeholder for game signature (can be extended later)
        analysis["game_signature"] = {
            "G1": 0.0,
            "G2": 0.0,
            "G3": 0.0,
            "G4": 0.0,
            "G5": 0.0,
            "G6": 0.0,
        }
        
        return analysis
    
    def _estimate_reading_level(self, word_count: int) -> str:
        """Estimate reading level based on word count."""
        if word_count < 500:
            return "elementary"
        elif word_count < 1500:
            return "middle"
        elif word_count < 3000:
            return "high_school"
        else:
            return "college"
    
    def _compute_complexity_score(self, post) -> float:
        """Compute a simple complexity score (0-1)."""
        score = 0.0
        
        # Word count factor (normalized)
        if post.word_count:
            word_score = min(post.word_count / 5000.0, 1.0) * 0.4
            score += word_score
        
        # Tags/categories diversity
        tag_count = len(post.tags_list) + len(post.categories_list)
        tag_score = min(tag_count / 10.0, 1.0) * 0.3
        score += tag_score
        
        # Content length variation (placeholder)
        score += 0.3
        
        return round(min(score, 1.0), 2)
    
    def _extract_slug_from_url(self, url: str) -> str:
        """Extract slug from blog post URL."""
        try:
            parsed = urlparse(url)
            path = parsed.path.strip("/")
            # Get last segment of path
            if path:
                segments = path.split("/")
                slug = segments[-1] if segments else ""
                # Remove file extension if present
                if "." in slug:
                    slug = slug.rsplit(".", 1)[0]
                return slug
            return ""
        except Exception:
            return ""
    
    def _get_existing_post_urls(self, posts_file: Path) -> Set[str]:
        """Get URLs of posts already in the JSONL file."""
        existing_urls = set()
        
        if not posts_file.exists():
            return existing_urls
        
        try:
            with open(posts_file, "r") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        post_data = json.loads(line)
                        if "post" in post_data and "url" in post_data["post"]:
                            existing_urls.add(post_data["post"]["url"])
                    except json.JSONDecodeError:
                        continue
        except Exception as e:
            logger.warning(f"Error reading existing posts: {e}")
        
        return existing_urls
    
    def update_meta_json(self, repo_path: str, user_id: str, new_posts_count: int = 0) -> None:
        """Update meta.json with sync information."""
        repo = Path(repo_path)
        meta_file = repo / "meta.json"
        
        # Read existing meta.json or create new
        if meta_file.exists():
            with open(meta_file, "r") as f:
                meta_data = json.load(f)
        else:
            meta_data = {
                "schema_version": self.schema_version,
                "user_id": user_id,
                "repositories": {},
            }
        
        # Count total posts in JSONL
        posts_file = repo / "artifacts" / "blog" / "posts.jsonl"
        total_posts = 0
        if posts_file.exists():
            with open(posts_file, "r") as f:
                total_posts = sum(1 for line in f if line.strip())
        
        # Update blog repository info
        meta_data["last_sync"] = datetime.utcnow().isoformat() + "Z"
        meta_data["repositories"]["blog"] = {
            "last_export": datetime.utcnow().isoformat() + "Z",
            "total_posts": total_posts,
        }
        
        # Write back
        with open(meta_file, "w") as f:
            json.dump(meta_data, f, indent=2)
    
    def is_git_repository(self, repo_path: str) -> bool:
        """Check if path is a Git repository."""
        repo = Path(repo_path)
        git_dir = repo / ".git"
        return git_dir.exists() or git_dir.is_dir()
    
    def commit_to_git(self, repo_path: str, message: str = "Add blog posts") -> bool:
        """
        Commit changes to Git repository.
        
        Args:
            repo_path: Path to repository
            message: Commit message
        
        Returns:
            True if successful, False otherwise
        """
        try:
            repo = Path(repo_path)
            
            # Check if Git repo
            if not self.is_git_repository(repo_path):
                logger.warning(f"Not a Git repository: {repo_path}")
                return False
            
            # Add all new/modified files
            subprocess.run(
                ["git", "add", "-A"],
                cwd=repo,
                check=True,
                capture_output=True,
            )
            
            # Commit
            result = subprocess.run(
                ["git", "commit", "-m", message],
                cwd=repo,
                capture_output=True,
                text=True,
            )
            
            if result.returncode == 0:
                logger.info(f"Committed changes to Git: {message}")
                return True
            elif "nothing to commit" in result.stdout.lower():
                logger.info("No changes to commit")
                return True
            else:
                logger.error(f"Git commit failed: {result.stderr}")
                return False
                
        except subprocess.CalledProcessError as e:
            logger.error(f"Git operation failed: {e}")
            return False
        except Exception as e:
            logger.error(f"Error committing to Git: {e}")
            return False
    
    def push_to_git(self, repo_path: str) -> bool:
        """
        Push changes to Git remote.
        
        Args:
            repo_path: Path to repository
        
        Returns:
            True if successful, False otherwise
        """
        try:
            repo = Path(repo_path)
            
            if not self.is_git_repository(repo_path):
                logger.warning(f"Not a Git repository: {repo_path}")
                return False
            
            result = subprocess.run(
                ["git", "push"],
                cwd=repo,
                capture_output=True,
                text=True,
            )
            
            if result.returncode == 0:
                logger.info("Pushed changes to Git remote")
                return True
            else:
                logger.error(f"Git push failed: {result.stderr}")
                return False
                
        except Exception as e:
            logger.error(f"Error pushing to Git: {e}")
            return False
