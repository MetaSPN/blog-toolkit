"""Tests for analyzer module."""

import pytest
from pathlib import Path
from datetime import datetime, timedelta

from blog_toolkit.database import Database
from blog_toolkit.analyzer import BlogAnalyzer


@pytest.fixture
def test_db_with_data(tmp_path):
    """Create a test database with sample data."""
    db_path = tmp_path / "test.db"
    db = Database(db_path)
    
    # Add a blog
    blog = db.add_blog(name="Test Blog", url="https://example.com", author_name="Test Author")
    
    # Add some posts
    base_date = datetime.now()
    for i in range(5):
        db.add_post(
            blog_id=blog.id,
            title=f"Post {i+1}",
            url=f"https://example.com/post{i+1}",
            content="This is test content " * 10,  # ~50 words
            published_date=base_date - timedelta(days=i*7),
            word_count=50,
            reading_time=1,
        )
    
    return db, blog


def test_analyze_blog(test_db_with_data):
    """Test analyzing a blog."""
    db, blog = test_db_with_data
    analyzer = BlogAnalyzer(db)
    
    results = analyzer.analyze_blog(blog.id)
    
    assert "temporal" in results
    assert "content" in results
    assert results["total_posts"] == 5
