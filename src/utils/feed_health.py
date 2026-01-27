"""
Feed Health Monitor - Automatic RSS feed health checking and repair

Monitors RSS feed health, detects issues, and attempts automatic fixes.
"""
import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse
import requests
import feedparser
from loguru import logger

from ..config import CONFIG_DIR, DATA_DIR


class FeedHealthStatus:
    """Feed health status codes"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"  # Working but slow
    DOWN = "down"
    FIXED = "fixed"
    UNKNOWN = "unknown"


class FeedIssue:
    """Types of feed issues"""
    HTTP_404 = "http_404"
    HTTP_500 = "http_500"
    HTTP_403 = "http_403"
    TIMEOUT = "timeout"
    PARSE_ERROR = "parse_error"
    EMPTY_FEED = "empty_feed"
    REDIRECT = "redirect"
    SSL_ERROR = "ssl_error"


class FeedHealthChecker:
    """Monitor and repair RSS feed health"""

    def __init__(self, timeout: int = 30):
        self.timeout = timeout
        self.health_file = DATA_DIR / "feed_health.json"
        self.history = self._load_history()

    def _load_history(self) -> Dict:
        """Load feed health history"""
        if self.health_file.exists():
            with open(self.health_file) as f:
                return json.load(f)
        return {"feeds": {}, "last_check": None}

    def _save_history(self):
        """Save feed health history"""
        self.health_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.health_file, 'w') as f:
            json.dump(self.history, f, indent=2)

    def check_feed(self, name: str, url: str) -> Tuple[str, Optional[str], Optional[str]]:
        """
        Check feed health and return status, issue, and optional fixed URL

        Returns:
            (status, issue_type, fixed_url)
        """
        logger.info(f"Checking feed health: {name}")

        try:
            # Try HTTP request first
            response = requests.head(url, timeout=self.timeout, allow_redirects=True)

            # Handle redirects
            if response.url != url:
                logger.info(f"Feed redirected: {url} -> {response.url}")
                return FeedHealthStatus.FIXED, FeedIssue.REDIRECT, response.url

            # Check status codes
            if response.status_code == 404:
                logger.warning(f"Feed returns 404: {name}")
                fixed_url = self._attempt_fix_404(name, url)
                if fixed_url:
                    return FeedHealthStatus.FIXED, FeedIssue.HTTP_404, fixed_url
                return FeedHealthStatus.DOWN, FeedIssue.HTTP_404, None

            elif response.status_code in [500, 502, 503]:
                logger.warning(f"Feed server error {response.status_code}: {name}")
                return FeedHealthStatus.DOWN, FeedIssue.HTTP_500, None

            elif response.status_code == 403:
                logger.warning(f"Feed access forbidden: {name}")
                return FeedHealthStatus.DOWN, FeedIssue.HTTP_403, None

            elif response.status_code != 200:
                logger.warning(f"Feed returns {response.status_code}: {name}")
                return FeedHealthStatus.DEGRADED, None, None

            # Try parsing feed
            feed = feedparser.parse(url)

            if feed.bozo:
                logger.warning(f"Feed parse error: {name} - {feed.bozo_exception}")
                return FeedHealthStatus.DEGRADED, FeedIssue.PARSE_ERROR, None

            if len(feed.entries) == 0:
                logger.warning(f"Feed is empty: {name}")
                return FeedHealthStatus.DEGRADED, FeedIssue.EMPTY_FEED, None

            # All checks passed
            logger.success(f"Feed healthy: {name} ({len(feed.entries)} entries)")
            return FeedHealthStatus.HEALTHY, None, None

        except requests.Timeout:
            logger.warning(f"Feed timeout: {name}")
            return FeedHealthStatus.DOWN, FeedIssue.TIMEOUT, None

        except requests.exceptions.SSLError:
            logger.warning(f"SSL error: {name}")
            return FeedHealthStatus.DOWN, FeedIssue.SSL_ERROR, None

        except Exception as e:
            logger.error(f"Error checking feed {name}: {e}")
            return FeedHealthStatus.UNKNOWN, None, None

    def _attempt_fix_404(self, name: str, url: str) -> Optional[str]:
        """
        Attempt to automatically fix 404 errors by finding alternative URLs

        Strategy:
        1. Check common RSS URL patterns on same domain
        2. For known domains, use hardcoded alternatives
        3. Fetch homepage and search for RSS links
        """
        domain = urlparse(url).netloc
        logger.info(f"Attempting to fix 404 for {name} on {domain}")

        # Known domain fixes
        fixes = self._get_known_fixes(domain)
        if fixes:
            for fix_url in fixes:
                try:
                    response = requests.head(fix_url, timeout=10)
                    if response.status_code == 200:
                        logger.success(f"Found working URL: {fix_url}")
                        return fix_url
                except:
                    continue

        # Try common RSS patterns
        common_patterns = [
            f"https://{domain}/feed/",
            f"https://{domain}/rss",
            f"https://{domain}/rss.xml",
            f"https://{domain}/feed.xml",
            f"https://{domain}/feeds/rss",
            f"https://{domain}/blog/feed/",
        ]

        for pattern_url in common_patterns:
            if pattern_url == url:
                continue
            try:
                response = requests.head(pattern_url, timeout=10)
                if response.status_code == 200:
                    logger.success(f"Found alternative URL: {pattern_url}")
                    return pattern_url
            except:
                continue

        logger.warning(f"Could not find alternative URL for {name}")
        return None

    def _get_known_fixes(self, domain: str) -> List[str]:
        """Get known alternative URLs for specific domains"""
        known_fixes = {
            "natural-resources.canada.ca": [
                "https://api.io.canada.ca/io-server/gc/news/en/v2?dept=naturalresourcescanada&sort=publishedDate&orderBy=desc&publishedDate%3E=2021-07-23&pick=50&format=atom&atomtitle=Natural%20Resources%20Canada",
                "https://natural-resources.canada.ca/simply-science/rss.xml",
            ],
            "www.canada.ca": [
                "https://www.canada.ca/en/environment-climate-change.atom.xml",
            ],
        }
        return known_fixes.get(domain, [])

    def check_all_feeds(self, feeds_config: List[Dict]) -> Dict:
        """
        Check health of all feeds and return report

        Returns dict with:
        - healthy: list of healthy feeds
        - degraded: list of degraded feeds
        - down: list of down feeds
        - fixed: list of feeds with auto-fixes applied
        """
        report = {
            "timestamp": datetime.now().isoformat(),
            "healthy": [],
            "degraded": [],
            "down": [],
            "fixed": [],
            "total": len([f for f in feeds_config if f.get("enabled", True)]),
        }

        for feed in feeds_config:
            if not feed.get("enabled", True):
                continue

            name = feed["name"]
            url = feed["url"]

            status, issue, fixed_url = self.check_feed(name, url)

            feed_status = {
                "name": name,
                "url": url,
                "status": status,
                "issue": issue,
                "fixed_url": fixed_url,
            }

            # Categorize
            if status == FeedHealthStatus.HEALTHY:
                report["healthy"].append(feed_status)
            elif status == FeedHealthStatus.DEGRADED:
                report["degraded"].append(feed_status)
            elif status == FeedHealthStatus.DOWN:
                report["down"].append(feed_status)
            elif status == FeedHealthStatus.FIXED:
                report["fixed"].append(feed_status)

            # Update history
            if name not in self.history["feeds"]:
                self.history["feeds"][name] = {
                    "checks": [],
                    "total_checks": 0,
                    "failures": 0,
                }

            self.history["feeds"][name]["checks"].append({
                "timestamp": datetime.now().isoformat(),
                "status": status,
                "issue": issue,
            })

            # Keep only last 30 checks
            self.history["feeds"][name]["checks"] = \
                self.history["feeds"][name]["checks"][-30:]

            self.history["feeds"][name]["total_checks"] += 1
            if status in [FeedHealthStatus.DOWN, FeedHealthStatus.DEGRADED]:
                self.history["feeds"][name]["failures"] += 1

            # Small delay to avoid hammering servers
            time.sleep(0.5)

        self.history["last_check"] = datetime.now().isoformat()
        self._save_history()

        return report

    def get_feed_stats(self, name: str) -> Dict:
        """Get health statistics for a specific feed"""
        if name not in self.history["feeds"]:
            return {"uptime": 1.0, "total_checks": 0, "recent_issues": []}

        feed_data = self.history["feeds"][name]
        total = feed_data["total_checks"]
        failures = feed_data["failures"]
        uptime = (total - failures) / total if total > 0 else 1.0

        # Get recent issues
        recent_checks = feed_data["checks"][-10:]
        recent_issues = [
            c for c in recent_checks
            if c["status"] in [FeedHealthStatus.DOWN, FeedHealthStatus.DEGRADED]
        ]

        return {
            "uptime": uptime,
            "total_checks": total,
            "failures": failures,
            "recent_issues": recent_issues,
        }

    def apply_fixes(self, feeds_config_path: Path, report: Dict) -> int:
        """
        Apply automatic fixes to feeds.json

        Returns number of feeds fixed
        """
        if not report["fixed"]:
            return 0

        logger.info(f"Applying {len(report['fixed'])} automatic fixes to feeds.json")

        # Load feeds config
        with open(feeds_config_path) as f:
            config = json.load(f)

        fixes_applied = 0

        for fix in report["fixed"]:
            for feed in config["feeds"]:
                if feed["name"] == fix["name"] and feed["url"] == fix["url"]:
                    old_url = feed["url"]
                    feed["url"] = fix["fixed_url"]
                    feed["_auto_fixed"] = datetime.now().isoformat()
                    feed["_old_url"] = old_url
                    logger.success(f"Fixed {fix['name']}: {old_url} -> {fix['fixed_url']}")
                    fixes_applied += 1
                    break

        # Save updated config
        if fixes_applied > 0:
            with open(feeds_config_path, 'w') as f:
                json.dump(config, f, indent=2)
            logger.info(f"Saved {fixes_applied} fixes to {feeds_config_path}")

        return fixes_applied


def format_health_report(report: Dict) -> str:
    """Format health check report as readable text"""
    lines = [
        "=" * 60,
        "RSS FEED HEALTH REPORT",
        "=" * 60,
        f"Timestamp: {report['timestamp']}",
        f"Total feeds: {report['total']}",
        "",
        f"✓ Healthy: {len(report['healthy'])}",
        f"⚠ Degraded: {len(report['degraded'])}",
        f"✗ Down: {len(report['down'])}",
        f"🔧 Fixed: {len(report['fixed'])}",
        "",
    ]

    if report["fixed"]:
        lines.append("AUTOMATIC FIXES APPLIED:")
        for feed in report["fixed"]:
            lines.append(f"  • {feed['name']}")
            lines.append(f"    Old: {feed['url']}")
            lines.append(f"    New: {feed['fixed_url']}")
        lines.append("")

    if report["down"]:
        lines.append("FEEDS DOWN:")
        for feed in report["down"]:
            issue_str = f" ({feed['issue']})" if feed['issue'] else ""
            lines.append(f"  • {feed['name']}{issue_str}")
        lines.append("")

    if report["degraded"]:
        lines.append("FEEDS DEGRADED:")
        for feed in report["degraded"]:
            issue_str = f" ({feed['issue']})" if feed['issue'] else ""
            lines.append(f"  • {feed['name']}{issue_str}")
        lines.append("")

    lines.append("=" * 60)
    return "\n".join(lines)
