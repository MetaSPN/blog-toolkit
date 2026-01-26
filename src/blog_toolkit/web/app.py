"""Flask web application for blog-toolkit dashboard."""

import json
from datetime import datetime

import plotly.graph_objs as go
from flask import Flask, jsonify, render_template, request

from blog_toolkit.analyzer import BlogAnalyzer
from blog_toolkit.collector import BlogCollector
from blog_toolkit.config import Config
from blog_toolkit.database import Database

app = Flask(__name__)
app.config["SECRET_KEY"] = "blog-toolkit-secret-key-change-in-production"

db = Database()
analyzer = BlogAnalyzer(db)
collector = BlogCollector(db)


@app.route("/")
def index():
    """Dashboard overview."""
    blogs = db.get_all_blogs()
    
    # Get post counts for each blog
    blog_data = []
    for blog in blogs:
        posts = db.get_posts_by_blog(blog.id)
        blog_data.append({
            "blog": blog,
            "post_count": len(posts),
        })
    
    # Get stats
    total_blogs = len(blogs)
    total_posts = sum(b["post_count"] for b in blog_data)
    authors = len(set(blog.author_name for blog in blogs if blog.author_name and blog.author_name.strip()))
    
    # Recent posts
    all_recent_posts = []
    for blog in blogs:
        posts = db.get_posts_by_blog(blog.id, limit=5)
        for post in posts:
            all_recent_posts.append({
                "blog_id": blog.id,
                "blog_name": blog.name,
                "title": post.title,
                "url": post.url,
                "published_date": post.published_date.isoformat() if post.published_date else None,
            })
    
    all_recent_posts.sort(key=lambda x: x["published_date"] or "", reverse=True)
    recent_posts = all_recent_posts[:10]
    
    return render_template(
        "dashboard.html",
        total_blogs=total_blogs,
        total_posts=total_posts,
        total_authors=authors,
        blog_data=blog_data,
        recent_posts=recent_posts,
    )


@app.route("/blog/<int:blog_id>")
def blog_detail(blog_id: int):
    """Blog detail page."""
    blog = db.get_blog(blog_id)
    if not blog:
        return "Blog not found", 404
    
    posts = db.get_posts_by_blog(blog_id)
    posts.sort(key=lambda x: x.published_date or datetime.min, reverse=True)
    
    # Get analysis
    analysis = analyzer.analyze_blog(blog_id)
    
    return render_template(
        "blog_detail.html",
        blog=blog,
        posts=posts,
        analysis=analysis,
    )


@app.route("/blog/<int:blog_id>/charts")
def blog_charts(blog_id: int):
    """Get chart data for a blog."""
    analysis = analyzer.analyze_blog(blog_id)
    
    charts = {}
    
    # Temporal chart - posts over time
    if "temporal" in analysis and "error" not in analysis["temporal"]:
        temp = analysis["temporal"]
        posts_by_month = temp.get("posts_per_month", {})
        if posts_by_month:
            months = sorted(posts_by_month.keys())
            counts = [posts_by_month[m] for m in months]
            charts["posts_over_time"] = {
                "data": [{"x": months, "y": counts, "type": "scatter", "mode": "lines+markers"}],
                "layout": {"title": "Posts Over Time", "xaxis": {"title": "Month"}, "yaxis": {"title": "Posts"}},
            }
    
    # Content chart - word count distribution
    if "content" in analysis and "error" not in analysis["content"]:
        cont = analysis["content"]
        trends = cont.get("content_trends", [])
        if trends:
            dates = [t["date"] for t in trends if t.get("date")]
            word_counts = [t["word_count"] for t in trends if t.get("word_count")]
            charts["word_count_trend"] = {
                "data": [{"x": dates, "y": word_counts, "type": "scatter", "mode": "lines+markers"}],
                "layout": {"title": "Word Count Trend", "xaxis": {"title": "Date"}, "yaxis": {"title": "Words"}},
            }
    
    # Topics chart - top keywords
    if "topics" in analysis and "error" not in analysis["topics"]:
        topics = analysis["topics"]
        keywords = topics.get("top_keywords", [])[:15]
        if keywords:
            words = [k[0] for k in keywords]
            counts = [k[1] for k in keywords]
            charts["top_keywords"] = {
                "data": [{"x": words, "y": counts, "type": "bar"}],
                "layout": {"title": "Top Keywords", "xaxis": {"title": "Keyword"}, "yaxis": {"title": "Count"}},
            }
    
    return jsonify(charts)


@app.route("/author/<author_name>")
def author_view(author_name: str):
    """Author view - all blogs by an author."""
    blogs = db.get_blogs_by_author(author_name)
    if not blogs:
        return "Author not found", 404
    
    # Get post counts for each blog
    blog_data = []
    for blog in blogs:
        posts = db.get_posts_by_blog(blog.id)
        blog_data.append({
            "blog": blog,
            "post_count": len(posts),
        })
    
    # Get analysis
    analysis = analyzer.analyze_author(author_name)
    
    return render_template(
        "author.html",
        author_name=author_name,
        blog_data=blog_data,
        analysis=analysis,
    )


@app.route("/compare")
def compare_view():
    """Blog comparison view."""
    blogs = db.get_all_blogs()
    blog_id1 = request.args.get("blog1", type=int)
    blog_id2 = request.args.get("blog2", type=int)
    
    comparison = None
    if blog_id1 and blog_id2:
        comparison = analyzer.compare_blogs([blog_id1, blog_id2])
    
    return render_template(
        "compare.html",
        blogs=blogs,
        comparison=comparison,
        selected_blog1=blog_id1,
        selected_blog2=blog_id2,
    )


@app.route("/api/blogs")
def api_blogs():
    """API endpoint for blogs list."""
    blogs = db.get_all_blogs()
    return jsonify([
        {
            "id": blog.id,
            "name": blog.name,
            "url": blog.url,
            "author_name": blog.author_name,
            "post_count": len(db.get_posts_by_blog(blog.id)),
        }
        for blog in blogs
    ])


@app.route("/api/blog/<int:blog_id>/add", methods=["POST"])
def api_add_blog(blog_id: int):
    """API endpoint to add/update a blog."""
    try:
        count = collector.update_blog(blog_id)
        return jsonify({"success": True, "new_posts": count})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400


def run_server(host=None, port=None, debug=None):
    """Run the Flask development server."""
    host = host or Config.WEB_HOST
    port = port or Config.WEB_PORT
    debug = debug if debug is not None else Config.WEB_DEBUG
    
    app.run(host=host, port=port, debug=debug)


if __name__ == "__main__":
    run_server()
