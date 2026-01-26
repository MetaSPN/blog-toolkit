"""Database models and operations for blog-toolkit."""

import json
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
    func,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker

from blog_toolkit.config import Config

Base = declarative_base()


class Blog(Base):
    """Blog model."""
    
    __tablename__ = "blogs"
    
    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    url = Column(String(500), nullable=False)
    feed_url = Column(String(500), nullable=True)
    author_name = Column(String(255), nullable=True)
    collection_method = Column(String(50), nullable=False, default="auto")  # rss, crawler, auto
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_collected_at = Column(DateTime, nullable=True)
    
    posts = relationship("Post", back_populates="blog", cascade="all, delete-orphan")
    analyses = relationship("Analysis", back_populates="blog", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<Blog(id={self.id}, name='{self.name}', url='{self.url}')>"


class Post(Base):
    """Blog post model."""
    
    __tablename__ = "posts"
    
    id = Column(Integer, primary_key=True)
    blog_id = Column(Integer, ForeignKey("blogs.id"), nullable=False)
    title = Column(String(500), nullable=False)
    url = Column(String(1000), nullable=False, unique=True)
    content = Column(Text, nullable=True)
    published_date = Column(DateTime, nullable=True)
    author = Column(String(255), nullable=True)
    word_count = Column(Integer, nullable=True)
    reading_time = Column(Integer, nullable=True)  # in minutes
    tags = Column(Text, nullable=True)  # comma-separated
    categories = Column(Text, nullable=True)  # comma-separated
    metadata_json = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    blog = relationship("Blog", back_populates="posts")
    
    def __repr__(self):
        return f"<Post(id={self.id}, title='{self.title[:50]}...', blog_id={self.blog_id})>"
    
    @property
    def tags_list(self) -> List[str]:
        """Return tags as a list."""
        if not self.tags:
            return []
        return [tag.strip() for tag in self.tags.split(",")]
    
    @property
    def categories_list(self) -> List[str]:
        """Return categories as a list."""
        if not self.categories:
            return []
        return [cat.strip() for cat in self.categories.split(",")]


class Analysis(Base):
    """Analysis results cache model."""
    
    __tablename__ = "analyses"
    
    id = Column(Integer, primary_key=True)
    blog_id = Column(Integer, ForeignKey("blogs.id"), nullable=True)  # NULL for author-level analyses
    author_name = Column(String(255), nullable=True)  # For author-level analyses
    analysis_type = Column(String(100), nullable=False)  # e.g., 'temporal', 'content', 'sentiment', 'full'
    results_json = Column(JSON, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    blog = relationship("Blog", back_populates="analyses")
    
    def __repr__(self):
        return f"<Analysis(id={self.id}, type='{self.analysis_type}', blog_id={self.blog_id})>"


class Database:
    """Database operations manager."""
    
    def __init__(self, db_path: Optional[Path] = None):
        """Initialize database connection."""
        Config.ensure_data_dir()
        db_path = db_path or Config.DATABASE_PATH
        self.engine = create_engine(f"sqlite:///{db_path}", echo=False)
        self.SessionLocal = sessionmaker(bind=self.engine)
        Base.metadata.create_all(self.engine)
    
    def get_session(self):
        """Get a database session."""
        return self.SessionLocal()
    
    def add_blog(
        self,
        name: str,
        url: str,
        feed_url: Optional[str] = None,
        author_name: Optional[str] = None,
        collection_method: str = "auto",
    ) -> Blog:
        """Add a new blog."""
        session = self.get_session()
        try:
            blog = Blog(
                name=name,
                url=url,
                feed_url=feed_url,
                author_name=author_name,
                collection_method=collection_method,
            )
            session.add(blog)
            session.commit()
            session.refresh(blog)
            return blog
        finally:
            session.close()
    
    def get_blog(self, blog_id: int) -> Optional[Blog]:
        """Get a blog by ID."""
        session = self.get_session()
        try:
            return session.query(Blog).filter(Blog.id == blog_id).first()
        finally:
            session.close()
    
    def get_all_blogs(self) -> List[Blog]:
        """Get all blogs."""
        session = self.get_session()
        try:
            return session.query(Blog).all()
        finally:
            session.close()
    
    def get_blogs_by_author(self, author_name: str) -> List[Blog]:
        """Get all blogs by an author."""
        session = self.get_session()
        try:
            return session.query(Blog).filter(Blog.author_name == author_name).all()
        finally:
            session.close()
    
    def add_post(
        self,
        blog_id: int,
        title: str,
        url: str,
        content: Optional[str] = None,
        published_date: Optional[datetime] = None,
        author: Optional[str] = None,
        word_count: Optional[int] = None,
        reading_time: Optional[int] = None,
        tags: Optional[List[str]] = None,
        categories: Optional[List[str]] = None,
        metadata: Optional[dict] = None,
    ) -> Post:
        """Add a new post (or update if URL exists)."""
        session = self.get_session()
        try:
            # Check if post already exists
            existing = session.query(Post).filter(Post.url == url).first()
            if existing:
                # Update existing post
                existing.title = title
                existing.content = content
                existing.published_date = published_date
                existing.author = author
                existing.word_count = word_count
                existing.reading_time = reading_time
                existing.tags = ",".join(tags) if tags else None
                existing.categories = ",".join(categories) if categories else None
                existing.metadata_json = metadata
                session.commit()
                session.refresh(existing)
                return existing
            
            # Create new post
            post = Post(
                blog_id=blog_id,
                title=title,
                url=url,
                content=content,
                published_date=published_date,
                author=author,
                word_count=word_count,
                reading_time=reading_time,
                tags=",".join(tags) if tags else None,
                categories=",".join(categories) if categories else None,
                metadata_json=metadata,
            )
            session.add(post)
            session.commit()
            session.refresh(post)
            return post
        finally:
            session.close()
    
    def get_posts_by_blog(self, blog_id: int, limit: Optional[int] = None) -> List[Post]:
        """Get posts for a blog."""
        session = self.get_session()
        try:
            query = session.query(Post).filter(Post.blog_id == blog_id).order_by(Post.published_date.desc())
            if limit:
                query = query.limit(limit)
            return query.all()
        finally:
            session.close()
    
    def update_blog_collection_time(self, blog_id: int) -> None:
        """Update the last collection time for a blog."""
        session = self.get_session()
        try:
            blog = session.query(Blog).filter(Blog.id == blog_id).first()
            if blog:
                blog.last_collected_at = datetime.utcnow()
                blog.updated_at = datetime.utcnow()
                session.commit()
        finally:
            session.close()
    
    def save_analysis(
        self,
        analysis_type: str,
        results: dict,
        blog_id: Optional[int] = None,
        author_name: Optional[str] = None,
    ) -> Analysis:
        """Save analysis results."""
        session = self.get_session()
        try:
            analysis = Analysis(
                blog_id=blog_id,
                author_name=author_name,
                analysis_type=analysis_type,
                results_json=results,
            )
            session.add(analysis)
            session.commit()
            session.refresh(analysis)
            return analysis
        finally:
            session.close()
    
    def get_latest_analysis(
        self,
        analysis_type: str,
        blog_id: Optional[int] = None,
        author_name: Optional[str] = None,
    ) -> Optional[Analysis]:
        """Get the latest analysis of a given type."""
        session = self.get_session()
        try:
            query = session.query(Analysis).filter(Analysis.analysis_type == analysis_type)
            if blog_id:
                query = query.filter(Analysis.blog_id == blog_id)
            if author_name:
                query = query.filter(Analysis.author_name == author_name)
            return query.order_by(Analysis.created_at.desc()).first()
        finally:
            session.close()
    
    def clean_post_content(self, post_id: int) -> bool:
        """
        Clean HTML from a single post's content.
        
        Args:
            post_id: Post ID to clean
        
        Returns:
            True if content was cleaned, False otherwise
        """
        from blog_toolkit.content_cleaner import clean_html, is_html
        
        session = self.get_session()
        try:
            post = session.query(Post).filter(Post.id == post_id).first()
            if not post:
                return False
            
            if not post.content or not is_html(post.content):
                return False
            
            # Clean the content
            cleaned_content = clean_html(post.content, preserve_structure=True)
            
            # Update post
            post.content = cleaned_content
            
            # Recalculate word count and reading time
            if cleaned_content:
                post.word_count = len(cleaned_content.split())
                post.reading_time = max(1, post.word_count // 200)
            
            session.commit()
            return True
        finally:
            session.close()
    
    def clean_all_posts(self, blog_id: Optional[int] = None) -> int:
        """
        Clean HTML from all posts or posts from a specific blog.
        
        Args:
            blog_id: If provided, only clean posts from this blog
        
        Returns:
            Number of posts cleaned
        """
        from blog_toolkit.content_cleaner import clean_html, is_html
        
        session = self.get_session()
        cleaned_count = 0
        try:
            query = session.query(Post)
            if blog_id:
                query = query.filter(Post.blog_id == blog_id)
            
            posts = query.all()
            
            for post in posts:
                if post.content and is_html(post.content):
                    # Clean the content
                    cleaned_content = clean_html(post.content, preserve_structure=True)
                    
                    # Update post
                    post.content = cleaned_content
                    
                    # Recalculate word count and reading time
                    if cleaned_content:
                        post.word_count = len(cleaned_content.split())
                        post.reading_time = max(1, post.word_count // 200)
                    
                    cleaned_count += 1
            
            session.commit()
            return cleaned_count
        finally:
            session.close()
    
    def get_posts_by_blog_with_filters(
        self,
        blog_id: int,
        min_word_count: Optional[int] = None,
        max_word_count: Optional[int] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        has_tags: Optional[bool] = None,
    ) -> List[Post]:
        """Get posts for a blog with optional filters."""
        session = self.get_session()
        try:
            query = session.query(Post).filter(Post.blog_id == blog_id)
            
            if min_word_count is not None:
                query = query.filter(Post.word_count >= min_word_count)
            if max_word_count is not None:
                query = query.filter(Post.word_count <= max_word_count)
            if date_from is not None:
                query = query.filter(Post.published_date >= date_from)
            if date_to is not None:
                query = query.filter(Post.published_date <= date_to)
            if has_tags is not None:
                if has_tags:
                    query = query.filter(Post.tags.isnot(None)).filter(Post.tags != "")
                else:
                    query = query.filter((Post.tags.is_(None)) | (Post.tags == ""))
            
            return query.order_by(Post.published_date.desc()).all()
        finally:
            session.close()
    
    def get_all_posts(
        self,
        blog_ids: Optional[List[int]] = None,
        author_name: Optional[str] = None,
        min_word_count: Optional[int] = None,
    ) -> List[Post]:
        """Get posts across multiple blogs or by author."""
        session = self.get_session()
        try:
            query = session.query(Post)
            
            if blog_ids:
                query = query.filter(Post.blog_id.in_(blog_ids))
            elif author_name:
                # Get blogs by author first
                blogs = session.query(Blog).filter(Blog.author_name == author_name).all()
                if blogs:
                    blog_ids_list = [blog.id for blog in blogs]
                    query = query.filter(Post.blog_id.in_(blog_ids_list))
                else:
                    return []  # No blogs found for author
            
            if min_word_count is not None:
                query = query.filter(Post.word_count >= min_word_count)
            
            return query.order_by(Post.published_date.desc()).all()
        finally:
            session.close()
