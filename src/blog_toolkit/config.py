"""Configuration management for blog-toolkit."""

import os
from pathlib import Path
from typing import Optional


class Config:
    """Application configuration."""
    
    # Database
    DATABASE_PATH: Path = Path(os.getenv("BLOG_TOOLKIT_DB", "data/blogs.db"))
    
    # Collection settings
    DEFAULT_COLLECTION_METHOD: str = "auto"  # auto, rss, crawler
    CRAWLER_MAX_DEPTH: int = int(os.getenv("CRAWLER_MAX_DEPTH", "10"))
    CRAWLER_RESPECT_ROBOTS: bool = os.getenv("CRAWLER_RESPECT_ROBOTS", "true").lower() == "true"
    
    # Request settings
    REQUEST_TIMEOUT: int = int(os.getenv("REQUEST_TIMEOUT", "30"))
    REQUEST_RETRIES: int = int(os.getenv("REQUEST_RETRIES", "3"))
    REQUEST_DELAY: float = float(os.getenv("REQUEST_DELAY", "1.0"))
    
    # Analysis settings
    ENABLE_SENTIMENT: bool = os.getenv("ENABLE_SENTIMENT", "true").lower() == "true"
    ENABLE_TOPIC_MODELING: bool = os.getenv("ENABLE_TOPIC_MODELING", "true").lower() == "true"
    
    # Web dashboard
    WEB_HOST: str = os.getenv("WEB_HOST", "127.0.0.1")
    WEB_PORT: int = int(os.getenv("WEB_PORT", "5000"))
    WEB_DEBUG: bool = os.getenv("WEB_DEBUG", "false").lower() == "true"
    
    # Sampling settings
    SAMPLE_MAX_CONTENT_LENGTH: int = int(os.getenv("SAMPLE_MAX_CONTENT_LENGTH", "10000"))
    SAMPLE_STRATIFY_TIME_BUCKETS: int = int(os.getenv("SAMPLE_STRATIFY_TIME_BUCKETS", "3"))
    SAMPLE_MIN_WORD_COUNT: int = int(os.getenv("SAMPLE_MIN_WORD_COUNT", "100"))
    
    # Content cleaning settings
    CLEAN_HTML_ON_COLLECTION: bool = os.getenv("CLEAN_HTML_ON_COLLECTION", "true").lower() == "true"
    
    # MetaSPN settings
    METASPN_USER_ID: Optional[str] = os.getenv("METASPN_USER_ID")
    METASPN_SCHEMA_VERSION: str = os.getenv("METASPN_SCHEMA_VERSION", "1.0.0")
    METASPN_COMPUTE_ANALYSIS: bool = os.getenv("METASPN_COMPUTE_ANALYSIS", "false").lower() == "true"
    
    @classmethod
    def ensure_data_dir(cls) -> None:
        """Ensure the data directory exists."""
        cls.DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
