"""
RSS Feed Fetcher

Fetches and parses RSS/Atom feeds from configured sources.
Uses two-stage approach: get article list, then fetch full content.
"""
import feedparser
import requests
from datetime import datetime
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field
from loguru import logger

from ..config import config, RSSFeed


@dataclass
class Article:
    """Parsed article from RSS feed"""
    title: str
    url: str
    summary: str
    published: Optional[datetime]
    source_name: str
    source_url: str
    category: str
    language: Optional[str] = None
    author: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    full_content: Optional[str] = None  # Populated in Stage 2
    raw_entry: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "title": self.title,
            "url": self.url,
            "summary": self.summary,
            "published": self.published.isoformat() if self.published else None,
            "source_name": self.source_name,
            "source_url": self.source_url,
            "category": self.category,
            "language": self.language,
            "author": self.author,
            "tags": self.tags,
            "full_content": self.full_content
        }


class RSSFetcher:
    """Fetches articles from RSS feeds"""

    def __init__(self, timeout: int = 30):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            # Browser-like UA: Cloudflare/WAF in front of OBV Saguenay,
            # OBV Lac-Saint-Jean, Conservation de la nature Canada (and
            # likely others) intermittently 403s the bot UA. Live probes
            # confirm the same URLs return 200 with a browser UA. Match
            # the Clairview platform fix from April 2026.
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "application/rss+xml, application/atom+xml, application/xml;q=0.9, */*;q=0.8",
        })

    def fetch_feed(self, feed: RSSFeed) -> List[Article]:
        """
        Fetch and parse a single RSS feed.

        Args:
            feed: RSSFeed configuration object

        Returns:
            List of Article objects
        """
        if not feed.enabled:
            logger.debug(f"Skipping disabled feed: {feed.name}")
            return []

        logger.info(f"Fetching feed: {feed.name} ({feed.url})")

        try:
            # Fetch with custom headers
            response = self.session.get(feed.url, timeout=self.timeout)
            response.raise_for_status()

            # Parse feed
            parsed = feedparser.parse(response.content)

            if parsed.bozo and parsed.bozo_exception:
                logger.warning(f"Feed parse warning for {feed.name}: {parsed.bozo_exception}")

            articles = []
            for entry in parsed.entries:
                article = self._parse_entry(entry, feed)
                if article:
                    articles.append(article)

            logger.info(f"Fetched {len(articles)} articles from {feed.name}")
            return articles

        except requests.RequestException as e:
            logger.error(f"Failed to fetch {feed.name}: {e}")
            return []
        except Exception as e:
            logger.error(f"Error processing {feed.name}: {e}")
            return []

    def _parse_entry(self, entry: Dict, feed: RSSFeed) -> Optional[Article]:
        """Parse a single feed entry into an Article"""
        try:
            # Extract published date
            published = None
            if hasattr(entry, 'published_parsed') and entry.published_parsed:
                published = datetime(*entry.published_parsed[:6])
            elif hasattr(entry, 'updated_parsed') and entry.updated_parsed:
                published = datetime(*entry.updated_parsed[:6])

            # Extract summary (prefer content, fallback to summary)
            summary = ""
            if hasattr(entry, 'content') and entry.content:
                summary = entry.content[0].get('value', '')
            elif hasattr(entry, 'summary'):
                summary = entry.summary or ""

            # Extract author
            author = None
            if hasattr(entry, 'author'):
                author = entry.author
            elif hasattr(entry, 'authors') and entry.authors:
                author = entry.authors[0].get('name', '')

            # Extract tags
            tags = []
            if hasattr(entry, 'tags'):
                tags = [tag.get('term', '') for tag in entry.tags if tag.get('term')]

            return Article(
                title=entry.get('title', 'No Title'),
                url=entry.get('link', ''),
                summary=summary,
                published=published,
                source_name=feed.name,
                source_url=feed.url,
                category=feed.category,
                language=feed.language,
                author=author,
                tags=tags,
                raw_entry=dict(entry)
            )

        except Exception as e:
            logger.warning(f"Failed to parse entry: {e}")
            return None

    def fetch_all_feeds(self) -> List[Article]:
        """
        Fetch all enabled feeds from config.

        Returns:
            Combined list of articles from all feeds
        """
        all_articles = []

        # Sort by priority (1=highest)
        sorted_feeds = sorted(config.feeds, key=lambda f: f.priority)

        for feed in sorted_feeds:
            articles = self.fetch_feed(feed)
            all_articles.extend(articles)

        logger.info(f"Total articles fetched: {len(all_articles)}")
        return all_articles


# Convenience function
def fetch_all_rss() -> List[Article]:
    """Fetch articles from all configured RSS feeds"""
    fetcher = RSSFetcher()
    return fetcher.fetch_all_feeds()
