"""
Storage Manager

Handles saving and loading articles to/from local files.
Organizes data by date in JSON format.
"""
import json
from datetime import datetime, date
from pathlib import Path
from typing import List, Optional, Dict
from loguru import logger

from ..config import DATA_DIR
from ..models import ArticleModel, DailyDigest


class StorageManager:
    """Manages article storage in JSON files"""

    def __init__(self, data_dir: Optional[Path] = None):
        self.data_dir = data_dir or DATA_DIR
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def _get_date_dir(self, date_str: str) -> Path:
        """Get directory for a specific date"""
        dir_path = self.data_dir / date_str
        dir_path.mkdir(parents=True, exist_ok=True)
        return dir_path

    def _get_digest_path(self, date_str: str) -> Path:
        """Get path to daily digest file"""
        return self._get_date_dir(date_str) / "digest.json"

    def _get_articles_path(self, date_str: str, category: str) -> Path:
        """Get path to category articles file"""
        return self._get_date_dir(date_str) / f"articles_{category}.json"

    def save_digest(self, digest: DailyDigest) -> Path:
        """
        Save daily digest to file.

        Args:
            digest: DailyDigest to save

        Returns:
            Path to saved file
        """
        path = self._get_digest_path(digest.date)

        with open(path, 'w', encoding='utf-8') as f:
            json.dump(digest.model_dump(mode='json'), f, indent=2, default=str)

        logger.info(f"Saved digest to {path} ({digest.total_articles} articles)")
        return path

    def load_digest(self, date_str: str) -> Optional[DailyDigest]:
        """
        Load daily digest from file.

        Args:
            date_str: Date string (YYYY-MM-DD)

        Returns:
            DailyDigest if exists, None otherwise
        """
        path = self._get_digest_path(date_str)

        if not path.exists():
            logger.debug(f"No digest found for {date_str}")
            return None

        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return DailyDigest.model_validate(data)
        except Exception as e:
            logger.error(f"Failed to load digest for {date_str}: {e}")
            return None

    def save_articles(self, articles: List[ArticleModel], date_str: Optional[str] = None) -> Dict[str, Path]:
        """
        Save articles organized by category.

        Args:
            articles: List of articles to save
            date_str: Date string (defaults to today)

        Returns:
            Dict of category -> file path
        """
        if not date_str:
            date_str = datetime.now().strftime("%Y-%m-%d")

        # Group by category
        by_category: Dict[str, List[ArticleModel]] = {}
        for article in articles:
            cat = article.category
            if cat not in by_category:
                by_category[cat] = []
            by_category[cat].append(article)

        # Save each category
        paths = {}
        for category, cat_articles in by_category.items():
            path = self._get_articles_path(date_str, category)
            with open(path, 'w', encoding='utf-8') as f:
                data = [a.model_dump(mode='json') for a in cat_articles]
                json.dump(data, f, indent=2, default=str)
            paths[category] = path
            logger.info(f"Saved {len(cat_articles)} {category} articles to {path}")

        return paths

    def load_articles(self, date_str: str, category: Optional[str] = None) -> List[ArticleModel]:
        """
        Load articles for a date, optionally filtered by category.

        Args:
            date_str: Date string (YYYY-MM-DD)
            category: Optional category filter

        Returns:
            List of ArticleModel
        """
        date_dir = self._get_date_dir(date_str)
        articles = []

        if category:
            # Load specific category
            path = self._get_articles_path(date_str, category)
            if path.exists():
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    articles = [ArticleModel.model_validate(a) for a in data]
        else:
            # Load all categories
            for path in date_dir.glob("articles_*.json"):
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    articles.extend([ArticleModel.model_validate(a) for a in data])

        return articles

    def get_date_range(self, start: date, end: date) -> List[DailyDigest]:
        """
        Get all digests in a date range.

        Args:
            start: Start date
            end: End date (inclusive)

        Returns:
            List of DailyDigest objects
        """
        digests = []
        current = start
        while current <= end:
            date_str = current.strftime("%Y-%m-%d")
            digest = self.load_digest(date_str)
            if digest:
                digests.append(digest)
            current = current.replace(day=current.day + 1)
        return digests

    def list_available_dates(self) -> List[str]:
        """List all dates with stored data"""
        dates = []
        for path in self.data_dir.iterdir():
            if path.is_dir() and (path / "digest.json").exists():
                dates.append(path.name)
        return sorted(dates, reverse=True)


# Global storage instance
storage = StorageManager()
