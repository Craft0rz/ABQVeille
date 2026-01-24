"""
Content Extractor

Fetches full article content from URLs using trafilatura.
Handles rate limiting, timeouts, and error recovery.
"""
import time
import requests
from typing import List, Optional, Dict, Any
from loguru import logger
import trafilatura
from trafilatura.settings import use_config

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from ABQ.src.models.article import ArticleModel


class ContentExtractor:
    """Extracts full article content from URLs"""

    def __init__(self, timeout: int = 15, delay: float = 1.0):
        """
        Initialize content extractor.

        Args:
            timeout: Request timeout in seconds
            delay: Delay between requests in seconds (rate limiting)
        """
        self.timeout = timeout
        self.delay = delay
        self.stats = {
            "success": 0,
            "failed": 0,
            "skipped_existing": 0,
            "skipped_google_news": 0
        }

        # Configure trafilatura for better extraction
        self.config = use_config()
        self.config.set("DEFAULT", "EXTRACTION_TIMEOUT", str(timeout))

    def _is_google_news_url(self, url: str) -> bool:
        """
        Check if URL is a Google News redirect URL.

        Google News URLs require JavaScript and don't provide HTTP redirects.
        We skip these and rely on RSS summaries instead.

        Args:
            url: URL to check

        Returns:
            True if Google News URL, False otherwise
        """
        return "news.google.com" in url and "/articles/" in url

    def extract_content(self, url: str) -> Optional[str]:
        """
        Fetch and extract clean text from article URL.

        Args:
            url: Article URL to fetch

        Returns:
            Extracted text content or None if failed
        """
        if not url:
            return None

        # Skip Google News URLs (they require JavaScript, rely on RSS summaries)
        if self._is_google_news_url(url):
            logger.debug(f"Skipping Google News URL (using RSS summary): {url[:60]}...")
            return None

        try:
            # Fetch HTML
            downloaded = trafilatura.fetch_url(url)

            if not downloaded:
                logger.debug(f"Failed to download: {url}")
                return None

            # Extract text content
            text = trafilatura.extract(
                downloaded,
                include_comments=False,
                include_tables=True,
                no_fallback=False,
                favor_precision=True,
                config=self.config
            )

            if text and len(text) > 100:  # Minimum content threshold
                return text.strip()

            return None

        except Exception as e:
            logger.debug(f"Extraction error for {url}: {e}")
            return None

    def process_articles(
        self,
        articles: List[ArticleModel],
        skip_existing: bool = True
    ) -> List[ArticleModel]:
        """
        Process list of articles, populating full_content.

        Args:
            articles: List of ArticleModel objects
            skip_existing: Skip articles that already have full_content

        Returns:
            Updated list of articles with full_content populated
        """
        total = len(articles)
        logger.info(f"Processing {total} articles for content extraction")

        # Sort by priority (1=highest first)
        sorted_articles = sorted(articles, key=lambda a: a.priority)

        for i, article in enumerate(sorted_articles):
            # Skip if already has content
            if skip_existing and article.full_content:
                self.stats["skipped_existing"] += 1
                continue

            # Check for Google News URLs (skip and track separately)
            if self._is_google_news_url(article.url):
                self.stats["skipped_google_news"] += 1
                logger.debug(f"Skipping Google News: {article.title[:50]}...")
                continue

            # Rate limiting
            if i > 0:
                time.sleep(self.delay)

            # Progress logging
            if (i + 1) % 10 == 0:
                logger.info(f"Progress: {i + 1}/{total} articles processed")

            # Extract content
            content = self.extract_content(article.url)

            if content:
                article.full_content = content
                self.stats["success"] += 1
                logger.debug(f"Extracted: {article.title[:50]}...")
            else:
                self.stats["failed"] += 1
                logger.debug(f"Failed: {article.title[:50]}...")

        logger.info(f"Extraction complete: {self.stats}")
        return sorted_articles

    def get_stats(self) -> Dict[str, int]:
        """Return extraction statistics"""
        return self.stats.copy()

    def reset_stats(self):
        """Reset extraction statistics"""
        self.stats = {
            "success": 0,
            "failed": 0,
            "skipped_existing": 0,
            "skipped_google_news": 0
        }


# Convenience function
def extract_content(articles: List[ArticleModel]) -> List[ArticleModel]:
    """Extract full content for a list of articles"""
    extractor = ContentExtractor()
    return extractor.process_articles(articles)
