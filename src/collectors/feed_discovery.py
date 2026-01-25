"""
Feed Discovery - Découvre automatiquement les flux RSS sur des sites web
"""
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from typing import List, Dict, Optional
from loguru import logger
import feedparser
import time


class FeedDiscovery:
    """Découvre automatiquement les flux RSS/Atom sur des sites web"""

    def __init__(self, timeout: int = 10):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })

    def discover_feeds(self, url: str) -> List[Dict]:
        """
        Découvre tous les flux RSS/Atom disponibles sur un site

        Returns:
            List of dicts with 'url', 'title', 'type' keys
        """
        feeds = []

        # Method 1: Check common RSS paths
        common_paths = [
            '/rss', '/rss.xml', '/feed', '/feed.xml', '/feeds',
            '/atom.xml', '/index.rss', '/index.xml',
            '/rss/news', '/feed/news', '/actualites/rss'
        ]

        base_url = self._get_base_url(url)

        for path in common_paths:
            feed_url = urljoin(base_url, path)
            if self._validate_feed(feed_url):
                feeds.append({
                    'url': feed_url,
                    'title': self._get_feed_title(feed_url),
                    'type': 'auto-discovered',
                    'method': 'common_path'
                })

        # Method 2: Parse HTML for feed links
        try:
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')

            # Look for <link rel="alternate"> tags
            link_tags = soup.find_all('link', rel='alternate')
            for tag in link_tags:
                feed_type = tag.get('type', '')
                if 'rss' in feed_type.lower() or 'atom' in feed_type.lower():
                    feed_url = urljoin(url, tag.get('href', ''))
                    if self._validate_feed(feed_url):
                        feeds.append({
                            'url': feed_url,
                            'title': tag.get('title', self._get_feed_title(feed_url)),
                            'type': feed_type,
                            'method': 'html_link'
                        })

            # Look for RSS/Feed links in the page
            rss_links = soup.find_all('a', href=re.compile(r'(rss|feed|atom)', re.I))
            for link in rss_links:
                feed_url = urljoin(url, link.get('href', ''))
                if self._validate_feed(feed_url):
                    feeds.append({
                        'url': feed_url,
                        'title': link.get_text(strip=True) or self._get_feed_title(feed_url),
                        'type': 'rss',
                        'method': 'html_anchor'
                    })

        except Exception as e:
            logger.debug(f"Could not parse HTML from {url}: {e}")

        # Remove duplicates
        seen_urls = set()
        unique_feeds = []
        for feed in feeds:
            if feed['url'] not in seen_urls:
                seen_urls.add(feed['url'])
                unique_feeds.append(feed)

        logger.info(f"Discovered {len(unique_feeds)} feed(s) on {url}")
        return unique_feeds

    def _get_base_url(self, url: str) -> str:
        """Extrait l'URL de base (scheme + netloc)"""
        parsed = urlparse(url)
        return f"{parsed.scheme}://{parsed.netloc}"

    def _validate_feed(self, url: str) -> bool:
        """Vérifie qu'une URL est un flux RSS/Atom valide"""
        try:
            response = self.session.get(url, timeout=self.timeout)
            if response.status_code != 200:
                return False

            # Parse with feedparser
            feed = feedparser.parse(response.content)
            return bool(feed.entries) and not feed.bozo

        except Exception:
            return False

    def _get_feed_title(self, url: str) -> Optional[str]:
        """Récupère le titre d'un flux RSS"""
        try:
            response = self.session.get(url, timeout=self.timeout)
            feed = feedparser.parse(response.content)
            return feed.feed.get('title', urlparse(url).netloc)
        except Exception:
            return urlparse(url).netloc

    def discover_from_domains(self, domains: List[str], delay: float = 1.0) -> Dict[str, List[Dict]]:
        """
        Découvre les flux RSS pour une liste de domaines

        Args:
            domains: List of domain names
            delay: Delay between requests (seconds)

        Returns:
            Dict mapping domain to list of discovered feeds
        """
        results = {}

        for i, domain in enumerate(domains, 1):
            logger.info(f"[{i}/{len(domains)}] Discovering feeds for {domain}")

            # Try both http and https
            for scheme in ['https', 'http']:
                url = f"{scheme}://{domain}"
                try:
                    feeds = self.discover_feeds(url)
                    if feeds:
                        results[domain] = feeds
                        break
                except Exception as e:
                    logger.debug(f"Failed to discover feeds for {url}: {e}")

            # Rate limiting
            if delay and i < len(domains):
                time.sleep(delay)

        return results


import re  # Add this import at the top


if __name__ == "__main__":
    # Test
    discovery = FeedDiscovery()

    test_sites = [
        "https://www.uqam.ca",
        "https://nouvelles.umontreal.ca",
        "https://www.ledevoir.com",
    ]

    for site in test_sites:
        print(f"\n=== Testing {site} ===")
        feeds = discovery.discover_feeds(site)
        for feed in feeds:
            print(f"  {feed['title']}: {feed['url']}")
