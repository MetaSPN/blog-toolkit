"""Analysis engine for blog metrics and trends."""

import logging
from collections import Counter
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import pandas as pd
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

from blog_toolkit.database import Database

logger = logging.getLogger(__name__)

# Initialize NLTK resources (will download if needed)
try:
    import nltk
    from nltk.corpus import stopwords
    from nltk.tokenize import word_tokenize
    
    try:
        nltk.data.find("tokenizers/punkt")
    except LookupError:
        nltk.download("punkt", quiet=True)
    
    try:
        nltk.data.find("corpora/stopwords")
    except LookupError:
        nltk.download("stopwords", quiet=True)
    
    STOPWORDS = set(stopwords.words("english"))
except ImportError:
    logger.warning("NLTK not available, some features may be limited")
    STOPWORDS = set()


class BlogAnalyzer:
    """Analyzer for blog metrics and trends."""
    
    def __init__(self, db: Optional[Database] = None):
        """Initialize analyzer."""
        self.db = db or Database()
        self.sentiment_analyzer = SentimentIntensityAnalyzer()
    
    def analyze_blog(self, blog_id: int, use_cache: bool = True) -> Dict:
        """
        Perform comprehensive analysis on a single blog.
        
        Returns:
            Dictionary with all analysis results
        """
        blog = self.db.get_blog(blog_id)
        if not blog:
            raise ValueError(f"Blog with ID {blog_id} not found")
        
        # Check cache
        if use_cache:
            cached = self.db.get_latest_analysis("full", blog_id=blog_id)
            if cached:
                # Check if cache is recent (within 1 hour)
                age = datetime.utcnow() - cached.created_at
                if age < timedelta(hours=1):
                    logger.info(f"Using cached analysis for blog {blog_id}")
                    return cached.results_json
        
        posts = self.db.get_posts_by_blog(blog_id)
        if not posts:
            return {"error": "No posts found for this blog"}
        
        logger.info(f"Analyzing blog {blog.name} ({len(posts)} posts)")
        
        results = {
            "blog_id": blog_id,
            "blog_name": blog.name,
            "total_posts": len(posts),
            "temporal": self._analyze_temporal(posts),
            "content": self._analyze_content(posts),
            "topics": self._analyze_topics(posts),
            "sentiment": self._analyze_sentiment(posts),
        }
        
        # Cache results
        self.db.save_analysis("full", results, blog_id=blog_id)
        
        return results
    
    def analyze_author(self, author_name: str, use_cache: bool = True) -> Dict:
        """
        Analyze all blogs by an author.
        
        Returns:
            Dictionary with aggregated analysis results
        """
        blogs = self.db.get_blogs_by_author(author_name)
        if not blogs:
            raise ValueError(f"No blogs found for author: {author_name}")
        
        # Check cache
        if use_cache:
            cached = self.db.get_latest_analysis("author", author_name=author_name)
            if cached:
                age = datetime.utcnow() - cached.created_at
                if age < timedelta(hours=1):
                    logger.info(f"Using cached analysis for author {author_name}")
                    return cached.results_json
        
        # Collect all posts from all blogs
        all_posts = []
        blog_stats = []
        
        for blog in blogs:
            posts = self.db.get_posts_by_blog(blog.id)
            all_posts.extend(posts)
            blog_stats.append({
                "blog_id": blog.id,
                "blog_name": blog.name,
                "post_count": len(posts),
            })
        
        if not all_posts:
            return {"error": "No posts found for this author"}
        
        logger.info(f"Analyzing author {author_name} ({len(all_posts)} posts across {len(blogs)} blogs)")
        
        results = {
            "author_name": author_name,
            "total_blogs": len(blogs),
            "total_posts": len(all_posts),
            "blog_stats": blog_stats,
            "temporal": self._analyze_temporal(all_posts),
            "content": self._analyze_content(all_posts),
            "topics": self._analyze_topics(all_posts),
            "sentiment": self._analyze_sentiment(all_posts),
            "cross_blog_comparison": self._compare_blogs_internal(blogs),
        }
        
        # Cache results
        self.db.save_analysis("author", results, author_name=author_name)
        
        return results
    
    def compare_blogs(self, blog_ids: List[int]) -> Dict:
        """
        Compare multiple blogs.
        
        Returns:
            Dictionary with comparative analysis
        """
        if len(blog_ids) < 2:
            raise ValueError("Need at least 2 blogs to compare")
        
        blogs = [self.db.get_blog(bid) for bid in blog_ids]
        if any(b is None for b in blogs):
            raise ValueError("One or more blog IDs not found")
        
        comparison = {
            "blogs": [{"id": b.id, "name": b.name} for b in blogs],
            "metrics": {},
        }
        
        # Get posts for each blog
        blog_posts = {}
        for blog in blogs:
            posts = self.db.get_posts_by_blog(blog.id)
            blog_posts[blog.id] = posts
        
        # Compare temporal metrics
        comparison["metrics"]["temporal"] = {}
        for blog in blogs:
            posts = blog_posts[blog.id]
            comparison["metrics"]["temporal"][blog.id] = self._analyze_temporal(posts)
        
        # Compare content metrics
        comparison["metrics"]["content"] = {}
        for blog in blogs:
            posts = blog_posts[blog.id]
            comparison["metrics"]["content"][blog.id] = self._analyze_content(posts)
        
        # Compare topics
        comparison["metrics"]["topics"] = {}
        for blog in blogs:
            posts = blog_posts[blog.id]
            comparison["metrics"]["topics"][blog.id] = self._analyze_topics(posts)
        
        return comparison
    
    def _analyze_temporal(self, posts: List) -> Dict:
        """Analyze temporal patterns."""
        if not posts:
            return {}
        
        # Filter posts with published dates
        dated_posts = [p for p in posts if p.published_date]
        if not dated_posts:
            return {"error": "No posts with published dates"}
        
        # Sort by date
        dated_posts.sort(key=lambda x: x.published_date)
        
        dates = [p.published_date for p in dated_posts]
        first_post = dates[0]
        last_post = dates[-1]
        date_range = (last_post - first_post).days
        
        # Posting frequency
        posts_by_month = Counter()
        posts_by_weekday = Counter()
        posts_by_hour = Counter()
        
        for date in dates:
            posts_by_month[date.strftime("%Y-%m")] += 1
            posts_by_weekday[date.strftime("%A")] += 1
            posts_by_hour[date.hour] += 1
        
        # Calculate gaps between posts
        gaps = []
        for i in range(1, len(dates)):
            gap = (dates[i] - dates[i-1]).days
            gaps.append(gap)
        
        avg_gap = sum(gaps) / len(gaps) if gaps else 0
        
        return {
            "first_post": first_post.isoformat() if first_post else None,
            "last_post": last_post.isoformat() if last_post else None,
            "date_range_days": date_range,
            "total_posts": len(dated_posts),
            "posts_per_month": dict(posts_by_month.most_common()),
            "posts_by_weekday": dict(posts_by_weekday),
            "posts_by_hour": dict(posts_by_hour),
            "average_gap_days": round(avg_gap, 2),
            "min_gap_days": min(gaps) if gaps else 0,
            "max_gap_days": max(gaps) if gaps else 0,
        }
    
    def _analyze_content(self, posts: List) -> Dict:
        """Analyze content metrics."""
        if not posts:
            return {}
        
        word_counts = [p.word_count for p in posts if p.word_count]
        reading_times = [p.reading_time for p in posts if p.reading_time]
        
        # Calculate trends over time
        content_trends = []
        for post in sorted([p for p in posts if p.published_date], key=lambda x: x.published_date):
            if post.word_count:
                content_trends.append({
                    "date": post.published_date.isoformat() if post.published_date else None,
                    "word_count": post.word_count,
                    "reading_time": post.reading_time,
                })
        
        return {
            "total_posts": len(posts),
            "posts_with_content": len([p for p in posts if p.content]),
            "word_count": {
                "total": sum(word_counts) if word_counts else 0,
                "average": round(sum(word_counts) / len(word_counts), 2) if word_counts else 0,
                "min": min(word_counts) if word_counts else 0,
                "max": max(word_counts) if word_counts else 0,
                "median": sorted(word_counts)[len(word_counts) // 2] if word_counts else 0,
            },
            "reading_time": {
                "total_minutes": sum(reading_times) if reading_times else 0,
                "average_minutes": round(sum(reading_times) / len(reading_times), 2) if reading_times else 0,
                "min": min(reading_times) if reading_times else 0,
                "max": max(reading_times) if reading_times else 0,
            },
            "content_trends": content_trends,
        }
    
    def _analyze_topics(self, posts: List) -> Dict:
        """Analyze topics and keywords."""
        if not posts:
            return {}
        
        # Collect all text content
        all_text = []
        for post in posts:
            if post.content:
                all_text.append(post.content)
        
        if not all_text:
            return {"error": "No content available for topic analysis"}
        
        # Extract keywords
        keywords = self._extract_keywords(" ".join(all_text))
        
        # Analyze tags and categories
        all_tags = []
        all_categories = []
        for post in posts:
            all_tags.extend(post.tags_list)
            all_categories.extend(post.categories_list)
        
        tag_counts = Counter(all_tags)
        category_counts = Counter(all_categories)
        
        return {
            "top_keywords": keywords[:20],  # Top 20 keywords
            "tag_distribution": dict(tag_counts.most_common(20)),
            "category_distribution": dict(category_counts.most_common(20)),
            "total_unique_tags": len(set(all_tags)),
            "total_unique_categories": len(set(all_categories)),
        }
    
    def _extract_keywords(self, text: str, top_n: int = 20) -> List[tuple]:
        """Extract top keywords from text."""
        try:
            from nltk.tokenize import word_tokenize
            
            # Tokenize and filter
            words = word_tokenize(text.lower())
            words = [w for w in words if w.isalpha() and w not in STOPWORDS and len(w) > 3]
            
            # Count frequencies
            word_counts = Counter(words)
            return word_counts.most_common(top_n)
        except Exception as e:
            logger.error(f"Error extracting keywords: {e}")
            return []
    
    def _analyze_sentiment(self, posts: List) -> Dict:
        """Analyze sentiment of posts."""
        if not posts:
            return {}
        
        sentiments = []
        for post in posts:
            if post.content:
                # Analyze sentiment
                scores = self.sentiment_analyzer.polarity_scores(post.content)
                sentiments.append({
                    "post_id": post.id,
                    "title": post.title,
                    "compound": scores["compound"],
                    "positive": scores["pos"],
                    "neutral": scores["neu"],
                    "negative": scores["neg"],
                })
        
        if not sentiments:
            return {"error": "No content available for sentiment analysis"}
        
        # Calculate averages
        avg_compound = sum(s["compound"] for s in sentiments) / len(sentiments)
        avg_positive = sum(s["positive"] for s in sentiments) / len(sentiments)
        avg_neutral = sum(s["neutral"] for s in sentiments) / len(sentiments)
        avg_negative = sum(s["negative"] for s in sentiments) / len(sentiments)
        
        # Categorize overall sentiment
        if avg_compound >= 0.05:
            overall = "positive"
        elif avg_compound <= -0.05:
            overall = "negative"
        else:
            overall = "neutral"
        
        return {
            "overall_sentiment": overall,
            "average_compound": round(avg_compound, 3),
            "average_positive": round(avg_positive, 3),
            "average_neutral": round(avg_neutral, 3),
            "average_negative": round(avg_negative, 3),
            "total_analyzed": len(sentiments),
            "sentiment_distribution": {
                "positive": len([s for s in sentiments if s["compound"] > 0.05]),
                "neutral": len([s for s in sentiments if -0.05 <= s["compound"] <= 0.05]),
                "negative": len([s for s in sentiments if s["compound"] < -0.05]),
            },
        }
    
    def _compare_blogs_internal(self, blogs: List) -> Dict:
        """Internal method to compare blogs by the same author."""
        comparison = {}
        
        for blog in blogs:
            posts = self.db.get_posts_by_blog(blog.id)
            comparison[blog.id] = {
                "blog_name": blog.name,
                "post_count": len(posts),
                "avg_word_count": sum(p.word_count for p in posts if p.word_count) / len([p for p in posts if p.word_count]) if posts else 0,
                "total_word_count": sum(p.word_count for p in posts if p.word_count) if posts else 0,
            }
        
        return comparison
