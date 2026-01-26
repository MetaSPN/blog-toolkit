"""Tests for crawler module."""

import pytest
from blog_toolkit.crawler import BlogCrawler


@pytest.fixture
def crawler():
    """Create a crawler instance."""
    return BlogCrawler()


def test_crawler_initialization(crawler):
    """Test crawler initialization."""
    assert crawler is not None
    assert crawler.max_depth > 0
