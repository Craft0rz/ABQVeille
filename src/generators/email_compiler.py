"""
Email Compiler - Compiles DailyDigest into email-ready format.
"""
from datetime import datetime
from typing import List, Dict, Optional
from dataclasses import dataclass, field
from loguru import logger

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from ABQ.src.models.article import ArticleModel, DailyDigest
from ABQ.src.config import config

@dataclass
class CategorySection:
    """Category section for email rendering."""
    name: str
    display_name: str
    articles: List[ArticleModel] = field(default_factory=list)

@dataclass
class EmailContext:
    """Complete context for email template rendering."""
    date: str
    subject: str
    logo_url: Optional[str] = None
    article_count: int = 0
    source_count: int = 0
    executive_summary: List[ArticleModel] = field(default_factory=list)
    ai_executive_summary: Optional[str] = None  # AI-generated daily brief
    categories: List[CategorySection] = field(default_factory=list)
    sources: List[str] = field(default_factory=list)
    generated_at: datetime = field(default_factory=datetime.now)
    unsubscribe_url: Optional[str] = None
    preferences_url: Optional[str] = None

class EmailCompiler:
    """Compiles DailyDigest into EmailContext."""

    # Category display names (French)
    CATEGORY_DISPLAY = {
        'research': 'Recherche scientifique',
        'environment': 'Environnement et ecologie',
        'regulatory': 'Reglementation et politiques',
        'events': 'Evenements et conferences',
        'general': 'Actualites generales',
    }

    CATEGORY_ORDER = [
        'research', 'environment', 'regulatory', 'events', 'general'
    ]

    def __init__(self, max_per_category=10, max_summary=5, min_summary_score=0.2):
        self.max_per_category = max_per_category
        self.max_summary = max_summary
        self.min_summary_score = min_summary_score

    def compile(self, digest: DailyDigest) -> EmailContext:
        """
        Compile DailyDigest into EmailContext for rendering.

        Args:
            digest: DailyDigest containing articles

        Returns:
            EmailContext ready for template rendering
        """
        logger.info(f"Compiling email for {digest.date}")

        # Build executive summary from top articles
        top_articles = digest.get_top_articles(self.max_summary)
        executive_summary = [
            a for a in top_articles
            if a.relevancy_score >= self.min_summary_score
        ]

        # Build category sections
        categories = []
        for category_name in self.CATEGORY_ORDER:
            if category_name in digest.articles:
                articles = digest.articles[category_name]

                # Sort by relevancy score and limit
                sorted_articles = sorted(
                    articles,
                    key=lambda a: a.relevancy_score,
                    reverse=True
                )[:self.max_per_category]

                if sorted_articles:
                    categories.append(CategorySection(
                        name=category_name,
                        display_name=self.CATEGORY_DISPLAY.get(
                            category_name,
                            category_name.replace('_', ' ').title()
                        ),
                        articles=sorted_articles
                    ))

        # Collect unique sources
        sources = sorted(set(digest.sources_fetched))

        # Generate subject line
        subject = self._generate_subject(digest, executive_summary)

        # Build context
        context = EmailContext(
            date=digest.date,
            subject=subject,
            article_count=digest.total_articles,
            source_count=len(sources),
            executive_summary=executive_summary,
            ai_executive_summary=digest.executive_summary,  # AI-generated brief
            categories=categories,
            sources=sources,
            generated_at=datetime.now(),
            logo_url=None,  # ABQ logo URL placeholder
            unsubscribe_url="#",  # Placeholder
            preferences_url="#"   # Placeholder
        )

        logger.info(
            f"Compiled email: {context.article_count} articles, "
            f"{len(executive_summary)} in summary, {len(categories)} categories"
        )

        return context

    def _generate_subject(self, digest: DailyDigest, summary: List[ArticleModel]) -> str:
        """Generate email subject line."""
        # Parse date
        try:
            date_obj = datetime.strptime(digest.date, "%Y-%m-%d")
            date_str = date_obj.strftime("%d %B %Y")
        except ValueError:
            date_str = digest.date

        # Count high priority articles
        high_priority = sum(1 for a in summary if a.relevancy_score >= 0.7)

        if high_priority > 0:
            return f"ABQ Veille Scientifique - {date_str} ({high_priority} prioritaires)"
        else:
            return f"ABQ Veille Scientifique - {date_str}"
