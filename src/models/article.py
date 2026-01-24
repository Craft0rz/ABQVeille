"""
Data Models for ABQ Intelligence System

Pydantic models for articles, digests, and storage.
"""
from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, computed_field
import hashlib


class ArticleModel(BaseModel):
    """Article data model for storage"""
    # Identity
    id: str = ""  # Generated from URL hash
    url: str
    title: str

    # Content
    summary: str = ""
    full_content: Optional[str] = None

    # Metadata
    published: Optional[datetime] = None
    fetched_at: datetime = Field(default_factory=datetime.now)
    source_name: str
    source_url: str
    category: str  # research, environment, regulatory, events, general
    author: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    language: Optional[str] = None  # fr, en

    # Analysis (populated later)
    relevancy_score: float = 0.0
    keywords_matched: List[str] = Field(default_factory=list)
    priority: int = 3  # 1=high, 2=medium, 3=low

    # AI Analysis (populated by AI Analyst)
    ai_summary: Optional[str] = None  # 2-3 sentence expert summary
    scientific_impact: Optional[str] = None  # How this affects biologists
    impact_category: Optional[str] = None  # research, policy, opportunity, environment, career
    impact_level: Optional[str] = None  # high, medium, low, none - for filtering
    analyzed_at: Optional[datetime] = None

    def model_post_init(self, __context: Any) -> None:
        """Generate ID from URL after initialization"""
        if not self.id and self.url:
            self.id = self.generate_id(self.url)

    @staticmethod
    def generate_id(url: str) -> str:
        """Generate unique ID from URL"""
        return hashlib.sha256(url.encode()).hexdigest()[:16]

    @computed_field
    @property
    def date_str(self) -> str:
        """Date string for folder organization (YYYY-MM-DD)"""
        dt = self.published or self.fetched_at
        return dt.strftime("%Y-%m-%d")


class DailyDigest(BaseModel):
    """Daily digest containing all articles for a day"""
    date: str  # YYYY-MM-DD
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    # Counts by category
    total_articles: int = 0
    by_category: Dict[str, int] = Field(default_factory=dict)

    # Articles grouped by category
    articles: Dict[str, List[ArticleModel]] = Field(default_factory=dict)

    # Metadata
    sources_fetched: List[str] = Field(default_factory=list)
    fetch_errors: List[str] = Field(default_factory=list)

    # AI-generated content
    executive_summary: Optional[str] = None  # Daily executive brief

    def add_article(self, article: ArticleModel) -> bool:
        """
        Add article to digest.

        Returns:
            True if added, False if duplicate
        """
        category = article.category

        if category not in self.articles:
            self.articles[category] = []

        # Check for duplicate
        existing_ids = {a.id for a in self.articles[category]}
        if article.id in existing_ids:
            return False

        self.articles[category].append(article)
        self.total_articles += 1
        self.by_category[category] = self.by_category.get(category, 0) + 1
        self.updated_at = datetime.now()
        return True

    def get_top_articles(self, n: int = 10) -> List[ArticleModel]:
        """Get top N articles by relevancy score"""
        all_articles = []
        for articles in self.articles.values():
            all_articles.extend(articles)
        return sorted(all_articles, key=lambda a: a.relevancy_score, reverse=True)[:n]


class FeedStatus(BaseModel):
    """Status of a feed fetch operation"""
    name: str
    url: str
    success: bool
    articles_count: int = 0
    error_message: Optional[str] = None
    fetched_at: datetime = Field(default_factory=datetime.now)
