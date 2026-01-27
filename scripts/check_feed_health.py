#!/usr/bin/env python3
"""
Standalone Feed Health Checker Script

Usage:
    python scripts/check_feed_health.py              # Check all feeds
    python scripts/check_feed_health.py --fix        # Check and apply auto-fixes
    python scripts/check_feed_health.py --stats      # Show feed statistics
"""
import sys
import json
import argparse
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.utils.feed_health import FeedHealthChecker, format_health_report
from src.config import CONFIG_DIR
from loguru import logger


def main():
    parser = argparse.ArgumentParser(description="Check RSS feed health")
    parser.add_argument("--fix", action="store_true", help="Apply automatic fixes to feeds.json")
    parser.add_argument("--stats", action="store_true", help="Show feed statistics")
    parser.add_argument("--feed", type=str, help="Check specific feed by name")
    parser.add_argument("--timeout", type=int, default=30, help="Request timeout in seconds")
    args = parser.parse_args()

    feeds_config_path = CONFIG_DIR / "feeds.json"

    if not feeds_config_path.exists():
        logger.error(f"Feeds config not found: {feeds_config_path}")
        sys.exit(1)

    # Load feeds
    with open(feeds_config_path) as f:
        config = json.load(f)
        feeds = config.get("feeds", [])

    # Initialize checker
    checker = FeedHealthChecker(timeout=args.timeout)

    # Show stats mode
    if args.stats:
        print("\n" + "=" * 60)
        print("FEED HEALTH STATISTICS")
        print("=" * 60)
        for feed in feeds:
            if not feed.get("enabled", True):
                continue
            name = feed["name"]
            stats = checker.get_feed_stats(name)
            if stats["total_checks"] > 0:
                uptime_pct = stats["uptime"] * 100
                print(f"\n{name}")
                print(f"  Uptime: {uptime_pct:.1f}%")
                print(f"  Total checks: {stats['total_checks']}")
                print(f"  Failures: {stats['failures']}")
                if stats["recent_issues"]:
                    print(f"  Recent issues: {len(stats['recent_issues'])}")
        print("\n" + "=" * 60)
        return

    # Check specific feed
    if args.feed:
        feed = next((f for f in feeds if f["name"] == args.feed), None)
        if not feed:
            logger.error(f"Feed not found: {args.feed}")
            sys.exit(1)

        logger.info(f"Checking feed: {args.feed}")
        status, issue, fixed_url = checker.check_feed(feed["name"], feed["url"])

        print(f"\nFeed: {feed['name']}")
        print(f"URL: {feed['url']}")
        print(f"Status: {status}")
        if issue:
            print(f"Issue: {issue}")
        if fixed_url:
            print(f"Fixed URL: {fixed_url}")
        return

    # Check all feeds
    logger.info(f"Checking health of {len([f for f in feeds if f.get('enabled', True)])} feeds...")
    report = checker.check_all_feeds(feeds)

    # Print report
    print("\n" + format_health_report(report))

    # Apply fixes if requested
    if args.fix and report["fixed"]:
        fixes_applied = checker.apply_fixes(feeds_config_path, report)
        print(f"\n✓ Applied {fixes_applied} automatic fixes to {feeds_config_path}")
        print("  Run the script again to verify fixes")

    # Exit with error code if feeds are down
    if report["down"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
