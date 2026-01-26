"""Blog post sampling for clustering evaluation."""

import logging
import random
from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Optional

from blog_toolkit.config import Config
from blog_toolkit.database import Database

logger = logging.getLogger(__name__)


class BlogSampler:
    """Sample blog posts for clustering evaluation."""
    
    def __init__(self, db: Optional[Database] = None):
        """Initialize sampler."""
        self.db = db or Database()
        self.max_content_length = Config.SAMPLE_MAX_CONTENT_LENGTH
        self.time_buckets = Config.SAMPLE_STRATIFY_TIME_BUCKETS
        self.min_word_count = Config.SAMPLE_MIN_WORD_COUNT
    
    def sample_blog(
        self,
        blog_id: int,
        count: int,
        method: str = "stratified",
    ) -> Dict:
        """
        Sample posts from a single blog.
        
        Args:
            blog_id: Blog ID to sample from
            count: Number of posts to sample
            method: Sampling method ('stratified' or 'random')
        
        Returns:
            Dictionary with metadata and samples
        """
        blog = self.db.get_blog(blog_id)
        if not blog:
            raise ValueError(f"Blog with ID {blog_id} not found")
        
        # Get all posts, filtering by minimum word count
        posts = self.db.get_posts_by_blog_with_filters(
            blog_id,
            min_word_count=self.min_word_count,
        )
        
        if not posts:
            raise ValueError(f"No posts found for blog {blog_id} (after filtering)")
        
        if len(posts) < count:
            logger.warning(
                f"Only {len(posts)} posts available, sampling all of them (requested {count})"
            )
            count = len(posts)
        
        # Apply sampling method
        if method == "stratified":
            sampled_posts = self._stratified_sample(posts, count)
        elif method == "random":
            sampled_posts = self._random_sample(posts, count)
        else:
            raise ValueError(f"Unknown sampling method: {method}")
        
        # Convert to output format
        samples = [self._post_to_sample(post, blog) for post in sampled_posts]
        
        return {
            "metadata": {
                "sampled_at": datetime.utcnow().isoformat() + "Z",
                "method": method,
                "total_samples": len(samples),
                "blogs": [
                    {
                        "id": blog.id,
                        "name": blog.name,
                        "samples": len(samples),
                    }
                ],
            },
            "samples": samples,
        }
    
    def sample_cross_blog(
        self,
        blog_ids: List[int],
        count_per_blog: int,
        method: str = "stratified",
    ) -> Dict:
        """
        Sample posts across multiple blogs.
        
        Args:
            blog_ids: List of blog IDs to sample from
            count_per_blog: Number of posts to sample per blog
            method: Sampling method ('stratified' or 'random')
        
        Returns:
            Dictionary with metadata and samples
        """
        all_samples = []
        blog_metadata = []
        
        for blog_id in blog_ids:
            blog = self.db.get_blog(blog_id)
            if not blog:
                logger.warning(f"Blog {blog_id} not found, skipping")
                continue
            
            try:
                blog_samples = self.sample_blog(blog_id, count_per_blog, method)
                all_samples.extend(blog_samples["samples"])
                blog_metadata.append({
                    "id": blog.id,
                    "name": blog.name,
                    "samples": len(blog_samples["samples"]),
                })
            except ValueError as e:
                logger.warning(f"Could not sample from blog {blog_id}: {e}")
                continue
        
        return {
            "metadata": {
                "sampled_at": datetime.utcnow().isoformat() + "Z",
                "method": method,
                "total_samples": len(all_samples),
                "blogs": blog_metadata,
            },
            "samples": all_samples,
        }
    
    def sample_by_author(
        self,
        author_name: str,
        count_per_blog: int,
        method: str = "stratified",
    ) -> Dict:
        """
        Sample posts from all blogs by an author.
        
        Args:
            author_name: Author name to sample from
            count_per_blog: Number of posts to sample per blog
            method: Sampling method ('stratified' or 'random')
        
        Returns:
            Dictionary with metadata and samples
        """
        blogs = self.db.get_blogs_by_author(author_name)
        if not blogs:
            raise ValueError(f"No blogs found for author: {author_name}")
        
        blog_ids = [blog.id for blog in blogs]
        return self.sample_cross_blog(blog_ids, count_per_blog, method)
    
    def _stratified_sample(self, posts: List, count: int) -> List:
        """
        Stratified sampling ensuring temporal spread, thematic diversity, and content length diversity.
        
        Args:
            posts: List of Post objects
            count: Number of posts to sample
        
        Returns:
            List of sampled Post objects
        """
        if len(posts) <= count:
            return posts
        
        # Filter posts with dates for temporal stratification
        posts_with_dates = [p for p in posts if p.published_date]
        posts_without_dates = [p for p in posts if not p.published_date]
        
        if not posts_with_dates:
            # No dates available, fall back to random with length diversity
            return self._random_sample_with_length_diversity(posts, count)
        
        # Sort by date
        posts_with_dates.sort(key=lambda x: x.published_date)
        
        # Temporal stratification: divide into time buckets
        total_posts = len(posts_with_dates)
        bucket_size = total_posts // self.time_buckets
        buckets = []
        
        for i in range(self.time_buckets):
            start_idx = i * bucket_size
            if i == self.time_buckets - 1:
                # Last bucket gets remainder
                end_idx = total_posts
            else:
                end_idx = (i + 1) * bucket_size
            buckets.append(posts_with_dates[start_idx:end_idx])
        
        # Calculate samples per bucket (proportional)
        samples_per_bucket = []
        remaining = count
        for i, bucket in enumerate(buckets):
            if i == len(buckets) - 1:
                # Last bucket gets remainder
                samples_per_bucket.append(remaining)
            else:
                bucket_count = max(1, int(count * len(bucket) / total_posts))
                samples_per_bucket.append(min(bucket_count, len(bucket), remaining))
                remaining -= samples_per_bucket[-1]
        
        sampled = []
        
        # Sample from each bucket with thematic and length diversity
        for bucket, bucket_count in zip(buckets, samples_per_bucket):
            if bucket_count == 0:
                continue
            
            # Group by primary tag/category for thematic diversity
            tagged_posts = defaultdict(list)
            untagged_posts = []
            
            for post in bucket:
                tags = post.tags_list
                categories = post.categories_list
                primary_tag = (tags[0] if tags else None) or (categories[0] if categories else None)
                
                if primary_tag:
                    tagged_posts[primary_tag].append(post)
                else:
                    untagged_posts.append(post)
            
            # Sample from each tag group
            if tagged_posts:
                tag_groups = list(tagged_posts.values())
                # Shuffle to avoid always picking same tags first
                random.shuffle(tag_groups)
                
                samples_from_bucket = []
                tag_idx = 0
                
                while len(samples_from_bucket) < bucket_count and tag_idx < len(tag_groups):
                    tag_group = tag_groups[tag_idx % len(tag_groups)]
                    if tag_group:
                        # Pick one from this tag group
                        post = random.choice(tag_group)
                        if post not in samples_from_bucket:
                            samples_from_bucket.append(post)
                            tag_group.remove(post)
                    tag_idx += 1
                
                # Fill remaining with untagged or any remaining posts
                remaining_needed = bucket_count - len(samples_from_bucket)
                if remaining_needed > 0:
                    all_remaining = untagged_posts + [
                        p for group in tag_groups for p in group
                    ]
                    if all_remaining:
                        additional = self._random_sample_with_length_diversity(
                            all_remaining, remaining_needed
                        )
                        samples_from_bucket.extend(additional)
                
                sampled.extend(samples_from_bucket[:bucket_count])
            else:
                # No tags, use length diversity
                sampled.extend(
                    self._random_sample_with_length_diversity(bucket, bucket_count)
                )
        
        # Add posts without dates if we need more
        if len(sampled) < count and posts_without_dates:
            needed = count - len(sampled)
            additional = self._random_sample_with_length_diversity(
                posts_without_dates, min(needed, len(posts_without_dates))
            )
            sampled.extend(additional)
        
        return sampled[:count]
    
    def _random_sample(self, posts: List, count: int) -> List:
        """Simple random sampling."""
        if len(posts) <= count:
            return posts
        return random.sample(posts, count)
    
    def _random_sample_with_length_diversity(self, posts: List, count: int) -> List:
        """
        Random sampling with content length diversity.
        
        Ensures mix of short, medium, and long posts.
        """
        if len(posts) <= count:
            return posts
        
        # Group by word count
        posts_with_word_count = [p for p in posts if p.word_count]
        posts_without_word_count = [p for p in posts if not p.word_count]
        
        if not posts_with_word_count:
            return random.sample(posts, min(count, len(posts)))
        
        # Define length categories
        word_counts = [p.word_count for p in posts_with_word_count]
        if word_counts:
            min_words = min(word_counts)
            max_words = max(word_counts)
            threshold1 = min_words + (max_words - min_words) / 3
            threshold2 = min_words + 2 * (max_words - min_words) / 3
            
            short_posts = [p for p in posts_with_word_count if p.word_count < threshold1]
            medium_posts = [
                p
                for p in posts_with_word_count
                if threshold1 <= p.word_count < threshold2
            ]
            long_posts = [p for p in posts_with_word_count if p.word_count >= threshold2]
        else:
            short_posts = medium_posts = long_posts = []
        
        # Sample proportionally from each category
        sampled = []
        remaining = count
        
        categories = [
            ("short", short_posts),
            ("medium", medium_posts),
            ("long", long_posts),
        ]
        
        for cat_name, cat_posts in categories:
            if remaining <= 0:
                break
            if not cat_posts:
                continue
            
            # Proportional sampling
            cat_count = max(1, int(count * len(cat_posts) / len(posts_with_word_count)))
            cat_count = min(cat_count, len(cat_posts), remaining)
            
            if cat_count > 0:
                sampled.extend(random.sample(cat_posts, cat_count))
                remaining -= cat_count
        
        # Fill remaining with any posts
        if remaining > 0:
            all_remaining = [
                p
                for p in posts_with_word_count
                if p not in sampled
            ] + posts_without_word_count
            if all_remaining:
                additional = random.sample(
                    all_remaining, min(remaining, len(all_remaining))
                )
                sampled.extend(additional)
        
        return sampled[:count]
    
    def _post_to_sample(self, post, blog) -> Dict:
        """Convert a Post object to sample format."""
        # Truncate content if needed
        content = post.content or ""
        if len(content) > self.max_content_length:
            content = content[: self.max_content_length] + "..."
        
        return {
            "id": f"blog_{blog.id}_post_{post.id}",
            "type": "blog",
            "content": content,
            "title": post.title,
            "timestamp": post.published_date.isoformat() + "Z" if post.published_date else None,
            "tags": post.tags_list,
            "author": post.author or blog.author_name,
            "blog_id": blog.id,
            "blog_name": blog.name,
            "word_count": post.word_count,
            "url": post.url,
        }
