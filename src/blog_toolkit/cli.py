"""CLI interface for blog-toolkit."""

import csv
import json
import logging
import sys
from pathlib import Path
from typing import Optional

import click
from tabulate import tabulate

from blog_toolkit.analyzer import BlogAnalyzer
from blog_toolkit.collector import BlogCollector
from blog_toolkit.config import Config
from blog_toolkit.database import Database
from blog_toolkit.metaspn_exporter import MetaSPNExporter
from blog_toolkit.sampler import BlogSampler
from blog_toolkit.content_cleaner import is_html

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@click.group()
@click.version_option(version="0.1.0")
def main():
    """Blog Toolkit - Collect, store, and analyze multiple blogs."""
    pass


@main.command()
@click.argument("url")
@click.option("--method", type=click.Choice(["rss", "crawler", "auto"]), default="auto", help="Collection method")
@click.option("--author", help="Author name")
@click.option("--name", help="Blog name (auto-detected if not provided)")
def add(url: str, method: str, author: Optional[str], name: Optional[str]):
    """Add a new blog to collect."""
    click.echo(f"Adding blog: {url}")
    
    try:
        collector = BlogCollector()
        blog_id = collector.collect_blog(url, method=method, author_name=author, blog_name=name)
        
        if blog_id:
            click.echo(click.style(f"✓ Successfully added blog (ID: {blog_id})", fg="green"))
        else:
            click.echo(click.style("✗ Failed to add blog", fg="red"), err=True)
            sys.exit(1)
    except Exception as e:
        click.echo(click.style(f"✗ Error: {e}", fg="red"), err=True)
        logger.exception("Error adding blog")
        sys.exit(1)


@main.command()
@click.argument("url")
@click.option("-o", "--output", "output_path", required=True, type=click.Path(), help="Output file or directory path")
@click.option("--format", "fmt", type=click.Choice(["json", "csv"]), default=None, help="Output format (default: infer from file extension)")
@click.option("--method", type=click.Choice(["rss", "crawler", "auto"]), default="auto", help="Collection method")
def pull(url: str, output_path: str, fmt: Optional[str], method: str):
    """Pull blog posts from a URL and write to file (no database required)."""
    try:
        collector = BlogCollector()
        blog_name, posts = collector.pull_posts(url, method=method)

        output = Path(output_path)

        # Infer format from extension if not specified
        if fmt is None:
            if output.suffix.lower() in (".json",):
                fmt = "json"
            elif output.suffix.lower() in (".csv",):
                fmt = "csv"
            else:
                fmt = "json"

        # Resolve output file path: if directory or path with no extension, write posts.{fmt} inside
        if output.suffix == "" or (output.exists() and output.is_dir()):
            output = output / f"posts.{fmt}"

        output.parent.mkdir(parents=True, exist_ok=True)

        # Serialize posts for output (aligned with orange-tpot field names)
        export_data = {
            "blog": {"name": blog_name, "url": url},
            "posts": [
                _post_to_orange_tpot(p)
                for p in posts
            ],
        }

        if fmt == "json":
            with open(output, "w") as f:
                json.dump(export_data, f, indent=2, default=str)
        else:
            with open(output, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["Blog", "Title", "URL", "Published Date", "Word Count", "Reading Time", "Tags"])
                for p in export_data["posts"]:
                    writer.writerow([
                        blog_name,
                        p["title"],
                        p["link"],
                        p["published"] or "",
                        p.get("word_count") or "",
                        p.get("reading_time") or "",
                        ",".join(p.get("tags", [])),
                    ])

        click.echo(click.style(f"✓ Pulled {len(posts)} posts to {output}", fg="green"))

    except ValueError as e:
        click.echo(click.style(f"✗ {e}", fg="red"), err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(click.style(f"✗ Error: {e}", fg="red"), err=True)
        logger.exception("Error pulling blog")
        sys.exit(1)


@main.command()
@click.option("--blog-id", type=int, help="Update specific blog by ID")
@click.option("--all", "update_all", is_flag=True, help="Update all blogs")
def update(blog_id: Optional[int], update_all: bool):
    """Update blog(s) by collecting new posts."""
    if not blog_id and not update_all:
        click.echo(click.style("Error: Must specify --blog-id or --all", fg="red"), err=True)
        sys.exit(1)
    
    try:
        collector = BlogCollector()
        db = Database()
        
        if update_all:
            blogs = db.get_all_blogs()
            click.echo(f"Updating {len(blogs)} blogs...")
            for blog in blogs:
                click.echo(f"Updating {blog.name}...")
                try:
                    count = collector.update_blog(blog.id)
                    click.echo(click.style(f"  ✓ Added {count} new posts", fg="green"))
                except Exception as e:
                    click.echo(click.style(f"  ✗ Error: {e}", fg="red"), err=True)
        else:
            click.echo(f"Updating blog ID {blog_id}...")
            count = collector.update_blog(blog_id)
            click.echo(click.style(f"✓ Added {count} new posts", fg="green"))
            
    except Exception as e:
        click.echo(click.style(f"✗ Error: {e}", fg="red"), err=True)
        logger.exception("Error updating blog")
        sys.exit(1)


@main.command()
@click.option("--blog-id", type=int, help="Analyze specific blog")
@click.option("--author", help="Analyze all blogs by author")
@click.option("--output", type=click.Path(), help="Save results to JSON file")
@click.option("--no-cache", is_flag=True, help="Don't use cached analysis")
def analyze(blog_id: Optional[int], author: Optional[str], output: Optional[str], no_cache: bool):
    """Run analysis on blog(s)."""
    if not blog_id and not author:
        click.echo(click.style("Error: Must specify --blog-id or --author", fg="red"), err=True)
        sys.exit(1)
    
    try:
        analyzer = BlogAnalyzer()
        
        if author:
            click.echo(f"Analyzing author: {author}")
            results = analyzer.analyze_author(author, use_cache=not no_cache)
        else:
            click.echo(f"Analyzing blog ID: {blog_id}")
            results = analyzer.analyze_blog(blog_id, use_cache=not no_cache)
        
        # Display results
        _display_analysis(results)
        
        # Save to file if requested
        if output:
            with open(output, "w") as f:
                json.dump(results, f, indent=2, default=str)
            click.echo(f"\nResults saved to {output}")
            
    except Exception as e:
        click.echo(click.style(f"✗ Error: {e}", fg="red"), err=True)
        logger.exception("Error analyzing")
        sys.exit(1)


@main.command()
def list_blogs():
    """List all blogs."""
    try:
        db = Database()
        blogs = db.get_all_blogs()
        
        if not blogs:
            click.echo("No blogs found.")
            return
        
        table_data = []
        for blog in blogs:
            post_count = len(db.get_posts_by_blog(blog.id))
            table_data.append([
                blog.id,
                blog.name,
                blog.url[:50] + "..." if len(blog.url) > 50 else blog.url,
                blog.author_name or "N/A",
                post_count,
                blog.collection_method,
                blog.last_collected_at.strftime("%Y-%m-%d %H:%M") if blog.last_collected_at else "Never",
            ])
        
        headers = ["ID", "Name", "URL", "Author", "Posts", "Method", "Last Collected"]
        click.echo(tabulate(table_data, headers=headers, tablefmt="grid"))
        
    except Exception as e:
        click.echo(click.style(f"✗ Error: {e}", fg="red"), err=True)
        logger.exception("Error listing blogs")
        sys.exit(1)


@main.command()
@click.argument("blog_id", type=int)
def show(blog_id: int):
    """Show details for a specific blog."""
    try:
        db = Database()
        blog = db.get_blog(blog_id)
        
        if not blog:
            click.echo(click.style(f"Blog with ID {blog_id} not found", fg="red"), err=True)
            sys.exit(1)
        
        posts = db.get_posts_by_blog(blog_id)
        
        click.echo(f"\nBlog: {blog.name}")
        click.echo(f"URL: {blog.url}")
        click.echo(f"Feed URL: {blog.feed_url or 'N/A'}")
        click.echo(f"Author: {blog.author_name or 'N/A'}")
        click.echo(f"Collection Method: {blog.collection_method}")
        click.echo(f"Total Posts: {len(posts)}")
        click.echo(f"Created: {blog.created_at}")
        click.echo(f"Last Updated: {blog.updated_at}")
        click.echo(f"Last Collected: {blog.last_collected_at or 'Never'}")
        
        if posts:
            click.echo(f"\nRecent Posts:")
            recent = sorted(posts, key=lambda x: x.published_date or datetime.min, reverse=True)[:10]
            for post in recent:
                date_str = post.published_date.strftime("%Y-%m-%d") if post.published_date else "N/A"
                click.echo(f"  - [{date_str}] {post.title[:60]}...")
        
    except Exception as e:
        click.echo(click.style(f"✗ Error: {e}", fg="red"), err=True)
        logger.exception("Error showing blog")
        sys.exit(1)


@main.command()
@click.argument("blog_id1", type=int)
@click.argument("blog_id2", type=int)
@click.option("--output", type=click.Path(), help="Save results to JSON file")
def compare(blog_id1: int, blog_id2: int, output: Optional[str]):
    """Compare two blogs."""
    try:
        analyzer = BlogAnalyzer()
        results = analyzer.compare_blogs([blog_id1, blog_id2])
        
        click.echo("\nBlog Comparison:")
        click.echo("=" * 60)
        
        for blog_info in results["blogs"]:
            click.echo(f"\nBlog {blog_info['id']}: {blog_info['name']}")
            metrics = results["metrics"]
            
            if "temporal" in metrics and blog_info["id"] in metrics["temporal"]:
                temp = metrics["temporal"][blog_info["id"]]
                click.echo(f"  Total Posts: {temp.get('total_posts', 0)}")
                click.echo(f"  Avg Gap (days): {temp.get('average_gap_days', 0)}")
            
            if "content" in metrics and blog_info["id"] in metrics["content"]:
                cont = metrics["content"][blog_info["id"]]
                wc = cont.get("word_count", {})
                click.echo(f"  Avg Word Count: {wc.get('average', 0)}")
                click.echo(f"  Total Words: {wc.get('total', 0)}")
        
        if output:
            with open(output, "w") as f:
                json.dump(results, f, indent=2, default=str)
            click.echo(f"\nComparison saved to {output}")
            
    except Exception as e:
        click.echo(click.style(f"✗ Error: {e}", fg="red"), err=True)
        logger.exception("Error comparing blogs")
        sys.exit(1)


@main.command()
@click.option("--format", type=click.Choice(["json", "csv"]), default="json", help="Export format")
@click.option("--output", type=click.Path(), required=True, help="Output file path")
@click.option("--blog-id", type=int, help="Export specific blog (all blogs if not specified)")
def export(format: str, output: str, blog_id: Optional[int]):
    """Export blog data."""
    try:
        db = Database()
        
        if blog_id:
            blogs = [db.get_blog(blog_id)]
            if not blogs[0]:
                raise ValueError(f"Blog {blog_id} not found")
        else:
            blogs = db.get_all_blogs()
        
        if format == "json":
            export_data = []
            for blog in blogs:
                posts = db.get_posts_by_blog(blog.id)
                export_data.append({
                    "blog": {
                        "id": blog.id,
                        "name": blog.name,
                        "url": blog.url,
                        "author": blog.author_name,
                    },
                    "posts": [
                        {
                            "title": post.title,
                            "url": post.url,
                            "published_date": post.published_date.isoformat() if post.published_date else None,
                            "word_count": post.word_count,
                            "reading_time": post.reading_time,
                            "tags": post.tags_list,
                            "categories": post.categories_list,
                        }
                        for post in posts
                    ],
                })
            
            with open(output, "w") as f:
                json.dump(export_data, f, indent=2, default=str)
        
        elif format == "csv":
            import csv
            with open(output, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["Blog", "Title", "URL", "Published Date", "Word Count", "Reading Time", "Tags"])
                
                for blog in blogs:
                    posts = db.get_posts_by_blog(blog.id)
                    for post in posts:
                        writer.writerow([
                            blog.name,
                            post.title,
                            post.url,
                            post.published_date.isoformat() if post.published_date else "",
                            post.word_count or "",
                            post.reading_time or "",
                            ",".join(post.tags_list),
                        ])
        
        click.echo(click.style(f"✓ Exported {len(blogs)} blog(s) to {output}", fg="green"))
        
    except Exception as e:
        click.echo(click.style(f"✗ Error: {e}", fg="red"), err=True)
        logger.exception("Error exporting")
        sys.exit(1)


@main.group()
def sample():
    """Sample blog posts for clustering evaluation."""
    pass


@sample.command("blog")
@click.argument("blog_id", type=int)
@click.option("--count", type=int, default=30, help="Number of posts to sample")
@click.option("--method", type=click.Choice(["stratified", "random"]), default="stratified", help="Sampling method")
@click.option("--output", type=click.Path(), required=True, help="Output JSON file path")
def sample_blog(blog_id: int, count: int, method: str, output: str):
    """Sample posts from a single blog."""
    try:
        sampler = BlogSampler()
        result = sampler.sample_blog(blog_id, count, method)
        
        # Save to file
        with open(output, "w") as f:
            json.dump(result, f, indent=2, default=str)
        
        click.echo(click.style(f"✓ Sampled {result['metadata']['total_samples']} posts from blog {blog_id}", fg="green"))
        click.echo(f"Results saved to {output}")
        
    except Exception as e:
        click.echo(click.style(f"✗ Error: {e}", fg="red"), err=True)
        logger.exception("Error sampling blog")
        sys.exit(1)


@sample.command("cross")
@click.option("--blog-ids", required=True, help="Comma-separated list of blog IDs (e.g., 1,2,3)")
@click.option("--count-per-blog", type=int, default=20, help="Number of posts to sample per blog")
@click.option("--method", type=click.Choice(["stratified", "random"]), default="stratified", help="Sampling method")
@click.option("--output", type=click.Path(), required=True, help="Output JSON file path")
def sample_cross(blog_ids: str, count_per_blog: int, method: str, output: str):
    """Sample posts across multiple blogs."""
    try:
        # Parse blog IDs
        blog_id_list = [int(bid.strip()) for bid in blog_ids.split(",")]
        
        sampler = BlogSampler()
        result = sampler.sample_cross_blog(blog_id_list, count_per_blog, method)
        
        # Save to file
        with open(output, "w") as f:
            json.dump(result, f, indent=2, default=str)
        
        click.echo(click.style(f"✓ Sampled {result['metadata']['total_samples']} posts across {len(blog_id_list)} blogs", fg="green"))
        for blog_info in result["metadata"]["blogs"]:
            click.echo(f"  - Blog {blog_info['id']} ({blog_info['name']}): {blog_info['samples']} samples")
        click.echo(f"Results saved to {output}")
        
    except Exception as e:
        click.echo(click.style(f"✗ Error: {e}", fg="red"), err=True)
        logger.exception("Error sampling cross-blog")
        sys.exit(1)


@sample.command("author")
@click.argument("author_name")
@click.option("--count-per-blog", type=int, default=25, help="Number of posts to sample per blog")
@click.option("--method", type=click.Choice(["stratified", "random"]), default="stratified", help="Sampling method")
@click.option("--output", type=click.Path(), required=True, help="Output JSON file path")
def sample_author(author_name: str, count_per_blog: int, method: str, output: str):
    """Sample posts from all blogs by an author."""
    try:
        sampler = BlogSampler()
        result = sampler.sample_by_author(author_name, count_per_blog, method)
        
        # Save to file
        with open(output, "w") as f:
            json.dump(result, f, indent=2, default=str)
        
        click.echo(click.style(f"✓ Sampled {result['metadata']['total_samples']} posts from {len(result['metadata']['blogs'])} blogs by {author_name}", fg="green"))
        for blog_info in result["metadata"]["blogs"]:
            click.echo(f"  - Blog {blog_info['id']} ({blog_info['name']}): {blog_info['samples']} samples")
        click.echo(f"Results saved to {output}")
        
    except Exception as e:
        click.echo(click.style(f"✗ Error: {e}", fg="red"), err=True)
        logger.exception("Error sampling by author")
        sys.exit(1)


@main.command()
@click.option("--blog-id", type=int, help="Clean posts from specific blog")
@click.option("--all", "clean_all", is_flag=True, help="Clean all posts")
@click.option("--dry-run", is_flag=True, help="Show what would be cleaned without making changes")
def clean(blog_id: Optional[int], clean_all: bool, dry_run: bool):
    """Clean HTML from blog post content."""
    if not blog_id and not clean_all:
        click.echo(click.style("Error: Must specify --blog-id or --all", fg="red"), err=True)
        sys.exit(1)
    
    try:
        db = Database()
        
        if clean_all:
            click.echo("Cleaning HTML from all posts...")
            if dry_run:
                # Count posts with HTML
                all_posts = []
                blogs = db.get_all_blogs()
                for blog in blogs:
                    posts = db.get_posts_by_blog(blog.id)
                    all_posts.extend(posts)
                
                html_posts = [p for p in all_posts if p.content and is_html(p.content)]
                click.echo(f"Would clean {len(html_posts)} posts with HTML content")
            else:
                cleaned_count = db.clean_all_posts()
                click.echo(click.style(f"✓ Cleaned HTML from {cleaned_count} posts", fg="green"))
        else:
            blog = db.get_blog(blog_id)
            if not blog:
                click.echo(click.style(f"Blog {blog_id} not found", fg="red"), err=True)
                sys.exit(1)
            
            click.echo(f"Cleaning HTML from posts in blog: {blog.name}")
            if dry_run:
                posts = db.get_posts_by_blog(blog_id)
                html_posts = [p for p in posts if p.content and is_html(p.content)]
                click.echo(f"Would clean {len(html_posts)} posts with HTML content")
            else:
                cleaned_count = db.clean_all_posts(blog_id=blog_id)
                click.echo(click.style(f"✓ Cleaned HTML from {cleaned_count} posts", fg="green"))
        
    except Exception as e:
        click.echo(click.style(f"✗ Error: {e}", fg="red"), err=True)
        logger.exception("Error cleaning HTML")
        sys.exit(1)


@main.group()
def push():
    """Push blog content to external repositories."""
    pass


@push.command("metaspn")
@click.argument("repo_path", type=click.Path())
@click.option("--blog-ids", help="Comma-separated list of blog IDs (e.g., 1,2,3)")
@click.option("--user-id", help="MetaSPN user ID (required if not in config)")
@click.option("--compute-analysis", is_flag=True, help="Compute game signatures and analysis")
@click.option("--git-push", is_flag=True, help="Push to Git remote after export")
def push_metaspn(repo_path: str, blog_ids: Optional[str], user_id: Optional[str], compute_analysis: bool, git_push: bool):
    """Push blog posts to MetaSPN content repository."""
    try:
        # Get user ID
        final_user_id = user_id or Config.METASPN_USER_ID
        if not final_user_id:
            click.echo(click.style("Error: --user-id required or set METASPN_USER_ID environment variable", fg="red"), err=True)
            sys.exit(1)
        
        # Parse blog IDs
        blog_id_list = None
        if blog_ids:
            blog_id_list = [int(bid.strip()) for bid in blog_ids.split(",")]
        
        # Initialize exporter
        exporter = MetaSPNExporter()
        
        # Export posts
        click.echo(f"Exporting posts to MetaSPN repository: {repo_path}")
        exported_count = exporter.export_posts(
            blog_id_list,
            repo_path,
            final_user_id,
            compute_analysis=compute_analysis or Config.METASPN_COMPUTE_ANALYSIS,
        )
        
        click.echo(click.style(f"✓ Exported {exported_count} posts to MetaSPN repository", fg="green"))
        
        # Handle Git operations
        if exporter.is_git_repository(repo_path):
            click.echo("Repository is a Git repository, committing changes...")
            if exporter.commit_to_git(repo_path, "Add blog posts via blog-toolkit"):
                if git_push:
                    click.echo("Pushing to Git remote...")
                    if exporter.push_to_git(repo_path):
                        click.echo(click.style("✓ Pushed to Git remote", fg="green"))
                    else:
                        click.echo(click.style("⚠ Failed to push to Git remote", fg="yellow"), err=True)
            else:
                click.echo(click.style("⚠ Failed to commit to Git", fg="yellow"), err=True)
        elif git_push:
            click.echo(click.style("⚠ Not a Git repository, skipping push", fg="yellow"), err=True)
        
    except Exception as e:
        click.echo(click.style(f"✗ Error: {e}", fg="red"), err=True)
        logger.exception("Error pushing to MetaSPN")
        sys.exit(1)


def _post_to_orange_tpot(p: dict) -> dict:
    """Convert internal post dict to orange-tpot expected format."""
    url = p["url"]
    published = p["published_date"].isoformat() if p.get("published_date") else None
    return {
        "title": p["title"],
        "link": url,  # orange-tpot expects link or url
        "url": url,
        "content": p["content"],
        "published": published,  # orange-tpot expects published/pub_date/published_at/date
        "published_date": published,  # backward compatibility
        "guid": url,  # orange-tpot uses guid/id for deduplication
        "author": p.get("author"),
        "word_count": p.get("word_count"),
        "reading_time": p.get("reading_time"),
        "tags": p.get("tags", []),
        "categories": p.get("categories", []),
    }


def _display_analysis(results: dict):
    """Display analysis results in a readable format."""
    if "error" in results:
        click.echo(click.style(f"Error: {results['error']}", fg="red"))
        return
    
    click.echo("\n" + "=" * 60)
    click.echo("ANALYSIS RESULTS")
    click.echo("=" * 60)
    
    if "blog_name" in results:
        click.echo(f"\nBlog: {results['blog_name']}")
    elif "author_name" in results:
        click.echo(f"\nAuthor: {results['author_name']}")
        click.echo(f"Blogs: {results.get('total_blogs', 0)}")
    
    click.echo(f"Total Posts: {results.get('total_posts', 0)}")
    
    # Temporal metrics
    if "temporal" in results and "error" not in results["temporal"]:
        temp = results["temporal"]
        click.echo(f"\n📅 Temporal Metrics:")
        click.echo(f"  Date Range: {temp.get('date_range_days', 0)} days")
        click.echo(f"  Average Gap: {temp.get('average_gap_days', 0)} days")
        click.echo(f"  First Post: {temp.get('first_post', 'N/A')}")
        click.echo(f"  Last Post: {temp.get('last_post', 'N/A')}")
    
    # Content metrics
    if "content" in results and "error" not in results["content"]:
        cont = results["content"]
        click.echo(f"\n📝 Content Metrics:")
        wc = cont.get("word_count", {})
        click.echo(f"  Total Words: {wc.get('total', 0):,}")
        click.echo(f"  Average Words: {wc.get('average', 0):,.0f}")
        click.echo(f"  Min/Max: {wc.get('min', 0)} / {wc.get('max', 0)}")
        rt = cont.get("reading_time", {})
        click.echo(f"  Avg Reading Time: {rt.get('average_minutes', 0):.1f} minutes")
    
    # Topics
    if "topics" in results and "error" not in results["topics"]:
        topics = results["topics"]
        click.echo(f"\n🏷️  Topics:")
        if "top_keywords" in topics:
            keywords = topics["top_keywords"][:10]
            click.echo(f"  Top Keywords: {', '.join([k[0] for k in keywords])}")
        if "tag_distribution" in topics:
            tags = list(topics["tag_distribution"].items())[:5]
            click.echo(f"  Top Tags: {', '.join([f'{t[0]} ({t[1]})' for t in tags])}")
    
    # Sentiment
    if "sentiment" in results and "error" not in results["sentiment"]:
        sent = results["sentiment"]
        click.echo(f"\n😊 Sentiment:")
        click.echo(f"  Overall: {sent.get('overall_sentiment', 'N/A').upper()}")
        click.echo(f"  Compound Score: {sent.get('average_compound', 0):.3f}")
        dist = sent.get("sentiment_distribution", {})
        click.echo(f"  Positive: {dist.get('positive', 0)}, Neutral: {dist.get('neutral', 0)}, Negative: {dist.get('negative', 0)}")
    
    click.echo("\n" + "=" * 60)


if __name__ == "__main__":
    main()
