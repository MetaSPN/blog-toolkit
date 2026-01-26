"""Tests for database module."""

import pytest
from pathlib import Path
from datetime import datetime

from blog_toolkit.database import Database, Blog, Post


@pytest.fixture
def test_db(tmp_path):
    """Create a test database."""
    db_path = tmp_path / "test.db"
    db = Database(db_path)
    yield db
    # Cleanup handled by tmp_path fixture


def test_add_blog(test_db):
    """Test adding a blog."""
    blog = test_db.add_blog(
        name="Test Blog",
        url="https://example.com",
        author_name="Test Author",
    )
    assert blog.id is not None
    assert blog.name == "Test Blog"
    assert blog.url == "https://example.com"


def test_get_blog(test_db):
    """Test getting a blog."""
    blog = test_db.add_blog(name="Test Blog", url="https://example.com")
    retrieved = test_db.get_blog(blog.id)
    assert retrieved is not None
    assert retrieved.name == "Test Blog"


def test_add_post(test_db):
    """Test adding a post."""
    blog = test_db.add_blog(name="Test Blog", url="https://example.com")
    post = test_db.add_post(
        blog_id=blog.id,
        title="Test Post",
        url="https://example.com/post1",
        content="This is test content",
        word_count=5,
    )
    assert post.id is not None
    assert post.title == "Test Post"
    assert post.word_count == 5


def test_get_posts_by_blog(test_db):
    """Test getting posts for a blog."""
    blog = test_db.add_blog(name="Test Blog", url="https://example.com")
    test_db.add_post(blog_id=blog.id, title="Post 1", url="https://example.com/1")
    test_db.add_post(blog_id=blog.id, title="Post 2", url="https://example.com/2")
    
    posts = test_db.get_posts_by_blog(blog.id)
    assert len(posts) == 2
