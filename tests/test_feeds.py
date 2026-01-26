"""Tests for feeds module."""

import pytest
from blog_toolkit.feeds import FeedParser


@pytest.fixture
def feed_parser():
    """Create a feed parser instance."""
    return FeedParser()


def test_parse_feed_invalid_url(feed_parser):
    """Test parsing an invalid feed URL."""
    result = feed_parser.parse_feed("https://invalid-url-that-does-not-exist.com/feed")
    # Should return None or handle gracefully
    assert result is None or isinstance(result, dict)
