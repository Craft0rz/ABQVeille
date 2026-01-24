"""
Analysis Pipeline

Orchestrates content extraction, relevancy scoring, and AI analysis for daily articles.
"""
from datetime import datetime
from typing import Optional
from loguru import logger

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from ABQ.src.models.article import ArticleModel, DailyDigest
from ABQ.src.utils.storage import storage
from ABQ.src.analyzers.content_extractor import ContentExtractor
from ABQ.src.analyzers.relevancy_scorer import RelevancyScorer
from ABQ.src.analyzers.ai_analyst import AIAnalyst
from ABQ.src.analyzers.daily_summary import DailySummaryGenerator
from ABQ.src.utils.dedup import ContentDeduplicator
from ABQ.src.config import config


class AnalysisPipeline:
    """Orchestrates content extraction, relevancy scoring, and AI analysis"""

    def __init__(
        self,
        extract_content: bool = True,
        extraction_delay: float = 1.0,
        extraction_limit: Optional[int] = None,
        enable_ai_analysis: bool = True,
        test_mode: bool = False
    ):
        """
        Initialize analysis pipeline.

        Args:
            extract_content: Whether to fetch full article content
            extraction_delay: Delay between content fetches (rate limiting)
            extraction_limit: Max articles to extract content for (None=all)
            enable_ai_analysis: Whether to use AI for article analysis
            test_mode: If True, limit AI to 2 articles, skip daily summary
        """
        self.extract_content = extract_content
        self.extraction_delay = extraction_delay
        self.extraction_limit = extraction_limit
        self.enable_ai_analysis = enable_ai_analysis and config.ai.enabled
        self.test_mode = test_mode

        self.extractor = ContentExtractor(delay=extraction_delay)
        self.scorer = RelevancyScorer()
        self.deduplicator = ContentDeduplicator(similarity_threshold=0.40)

        # AI components (only initialized if enabled)
        if self.enable_ai_analysis:
            # In test mode, limit AI to test_max_articles
            max_articles = config.ai.test_max_articles if test_mode else config.ai.max_articles_to_analyze
            self.ai_analyst = AIAnalyst(max_articles=max_articles)
            self.summary_generator = DailySummaryGenerator() if not test_mode else None
        else:
            self.ai_analyst = None
            self.summary_generator = None

    def process_daily(self, date_str: Optional[str] = None) -> Optional[DailyDigest]:
        """
        Run full analysis pipeline for a day's articles.

        Args:
            date_str: Date to process (YYYY-MM-DD), defaults to today

        Returns:
            Updated DailyDigest with scored articles, or None if no data
        """
        if not date_str:
            date_str = datetime.now().strftime("%Y-%m-%d")

        logger.info(f"Starting analysis pipeline for {date_str}")

        # Stage 1: Load articles
        articles = storage.load_articles(date_str)
        if not articles:
            logger.warning(f"No articles found for {date_str}")
            return None

        logger.info(f"Loaded {len(articles)} articles")

        # Stage 1b: Filter to only articles published on target date
        articles = self._filter_by_date(articles, date_str)
        if not articles:
            logger.warning(f"No articles published on {date_str}")
            return None

        logger.info(f"Filtered to {len(articles)} articles from {date_str}")

        # Stage 1c: Deduplicate similar stories from different sources
        articles = self.deduplicator.deduplicate(articles)
        logger.info(f"After deduplication: {len(articles)} unique articles, {self.deduplicator.get_stats()}")

        # Stage 2: Extract full content (optional)
        if self.extract_content:
            if self.extraction_limit:
                # Only extract for top priority articles
                to_extract = articles[:self.extraction_limit]
                remaining = articles[self.extraction_limit:]
                articles = self.extractor.process_articles(to_extract) + remaining
            else:
                articles = self.extractor.process_articles(articles)

            logger.info(f"Content extraction: {self.extractor.get_stats()}")

        # Stage 3: Score for relevancy
        articles = self.scorer.score_batch(articles)

        # Stage 4: Filter relevant articles
        relevant = self.scorer.filter_relevant(articles)

        # Stage 5: AI Analysis (if enabled)
        executive_summary = None
        if self.enable_ai_analysis and relevant:
            logger.info(f"Running AI analysis on {len(relevant)} relevant articles")
            relevant = self.ai_analyst.analyze_batch(relevant)
            logger.info(f"AI analysis complete: {self.ai_analyst.get_stats()}")

            # Stage 6: Generate daily executive summary (skip in test mode)
            if self.summary_generator:
                logger.info("Generating daily executive summary")
                executive_summary = self.summary_generator.generate(relevant, date_str)
            else:
                logger.info("Skipping daily summary (test mode)")

        # Stage 7: Build and save digest
        digest = self._build_digest(articles, relevant, date_str, executive_summary)
        storage.save_digest(digest)

        # Also save updated articles (with AI analysis)
        storage.save_articles(articles, date_str)

        logger.info(f"Pipeline complete: {len(relevant)} relevant articles from {len(articles)} total")

        return digest

    def _filter_by_date(self, articles: list, date_str: str) -> list:
        """
        Filter articles to only those published on the target date.

        Args:
            articles: List of ArticleModel
            date_str: Target date (YYYY-MM-DD)

        Returns:
            Filtered list of articles
        """
        filtered = []
        for article in articles:
            if article.published:
                article_date = article.published.strftime("%Y-%m-%d")
                if article_date == date_str:
                    filtered.append(article)
            # If no published date, skip the article
        return filtered

    def _build_digest(
        self,
        all_articles: list,
        relevant_articles: list,
        date_str: str,
        executive_summary: Optional[str] = None
    ) -> DailyDigest:
        """Build DailyDigest from processed articles"""
        digest = DailyDigest(
            date=date_str,
            created_at=datetime.now(),
            updated_at=datetime.now(),
            total_articles=0,  # Will be incremented by add_article
            by_category={},
            articles={},
            sources_fetched=[],
            fetch_errors=[],
            executive_summary=executive_summary
        )

        # Group relevant articles by category
        for article in relevant_articles:
            digest.add_article(article)

        # Track sources
        sources = set(a.source_name for a in all_articles)
        digest.sources_fetched = sorted(list(sources))

        return digest


# Convenience function
def run_daily_analysis(date_str: Optional[str] = None) -> Optional[DailyDigest]:
    """Run analysis pipeline for today (or specified date)"""
    pipeline = AnalysisPipeline()
    return pipeline.process_daily(date_str)
