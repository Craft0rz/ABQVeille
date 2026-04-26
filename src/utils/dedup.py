"""
Article Deduplication - Content-Based

Detects and removes duplicate news stories from different sources
using title similarity matching.
"""
import re
import unicodedata
from typing import List, Set, Tuple, Dict
from loguru import logger

from ..models.article import ArticleModel


# French and English stop words to ignore in comparison
STOP_WORDS = {
    # French
    "le", "la", "les", "de", "du", "des", "un", "une", "et", "en", "au", "aux",
    "ce", "ces", "cette", "qui", "que", "sur", "pour", "par", "dans", "avec",
    "est", "sont", "a", "ont", "son", "sa", "ses", "leur", "leurs", "plus",
    # English
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for", "of",
    "is", "are", "was", "were", "be", "been", "has", "have", "had", "its",
    "this", "that", "these", "those", "with", "from", "by", "as", "it",
    # Generic high-frequency words that bloat Quebec/environment news
    "quebec", "quebecois", "canada", "canadien", "canadienne", "ans",
    "environnement", "environnemental", "environnementale", "ministere",
    "gouvernement", "nouvelle", "nouvelles", "nouveau", "nouveaux", "nouvelle",
    "nbsp", "amp", "x27", "etre", "fait", "faire", "tres", "deux", "trois",
    "selon", "entre", "chez", "vers", "tous", "toutes", "tout", "toute",
    "ici", "radio", "tva", "presse", "devoir", "journal",
}


class ContentDeduplicator:
    """Detects duplicate stories from different sources using title similarity"""

    def __init__(self, similarity_threshold: float = 0.25, min_shared_tokens: int = 4):
        """
        Initialize deduplicator.

        Args:
            similarity_threshold: Minimum Jaccard similarity to consider duplicate
            min_shared_tokens: Minimum number of shared tokens (absolute overlap)
                required in addition to the ratio threshold. Prevents short
                token sets with generic words from collapsing into giant groups.
        """
        self.similarity_threshold = similarity_threshold
        self.min_shared_tokens = min_shared_tokens
        self.duplicates_removed = 0
        self.duplicate_groups: List[List[ArticleModel]] = []

    def _normalize_text(self, text: str, strip_source_suffix: bool = False) -> Set[str]:
        """Normalize text into a set of comparable tokens."""
        if not text:
            return set()

        # Strip source suffix (Google News appends "- SourceName")
        if strip_source_suffix:
            text = re.sub(r'\s*[-–]\s*[A-Z][A-Za-z\s\-\.]*$', '', text)

        # Lowercase, strip accents, strip punctuation
        text = text.lower()
        text = unicodedata.normalize('NFD', text)
        text = ''.join(c for c in text if unicodedata.category(c) != 'Mn')
        text = re.sub(r'[<][^>]+[>]', ' ', text)  # strip any HTML tags
        text = re.sub(r'[^a-z0-9\s]', ' ', text)

        # Tokenize, drop stop words and short tokens
        return {t for t in text.split() if t not in STOP_WORDS and len(t) >= 3}

    def _article_tokens(self, article: ArticleModel) -> Set[str]:
        """Combine title + summary tokens for richer duplicate detection."""
        title_tokens = self._normalize_text(article.title or "", strip_source_suffix=True)
        summary_tokens = self._normalize_text(article.summary or "")
        return title_tokens | summary_tokens

    def _jaccard_similarity(self, set1: Set[str], set2: Set[str]) -> float:
        """Calculate Jaccard similarity between two token sets"""
        if not set1 or not set2:
            return 0.0
        intersection = len(set1 & set2)
        union = len(set1 | set2)
        return intersection / union if union > 0 else 0.0

    def _find_duplicates(self, articles: List[ArticleModel]) -> List[List[int]]:
        """
        Find groups of duplicate articles.

        Returns list of index groups where each group contains duplicate articles.
        """
        n = len(articles)
        # Pre-compute normalized token sets (title + summary)
        normalized = [self._article_tokens(a) for a in articles]

        # Track which articles have been grouped
        grouped: Set[int] = set()
        groups: List[List[int]] = []

        for i in range(n):
            if i in grouped:
                continue

            # Start a new group with this article
            group = [i]
            grouped.add(i)

            # Find all similar articles
            for j in range(i + 1, n):
                if j in grouped:
                    continue

                shared = len(normalized[i] & normalized[j])
                if shared < self.min_shared_tokens:
                    continue
                similarity = self._jaccard_similarity(normalized[i], normalized[j])
                if similarity >= self.similarity_threshold:
                    group.append(j)
                    grouped.add(j)

            if len(group) > 1:
                groups.append(group)

        return groups

    def _select_best_article(self, articles: List[ArticleModel], duplicate_count: int) -> ArticleModel:
        """
        Select the best article from a group of duplicates and boost its importance.

        Priority:
        1. Lowest priority number (1=high priority source)
        2. Has full content extracted
        3. Longer summary/content
        4. Earlier published date (first to report)

        The selected article will have:
        - Boosted relevancy score based on duplicate_count
        - Priority upgraded to 1 (high) if it appears in 3+ sources
        """
        def score(article: ArticleModel) -> Tuple:
            return (
                article.priority,  # Lower is better
                0 if article.full_content else 1,  # Has content is better
                -len(article.summary or ""),  # Longer is better (negative for min sort)
                article.published or article.fetched_at  # Earlier is better
            )

        best = min(articles, key=score)

        # Boost relevancy score based on how many sources shared this story
        # Each duplicate adds 0.3 to relevancy score (caps at 1.0)
        boost = min((duplicate_count - 1) * 0.3, 0.9)
        best.relevancy_score = min(best.relevancy_score + boost, 1.0)

        # Upgrade priority to HIGH if story appears in 3+ sources
        if duplicate_count >= 3 and best.priority > 1:
            logger.info(f"Upgrading priority: '{best.title[:50]}...' shared by {duplicate_count} sources")
            best.priority = 1

        return best

    def deduplicate(self, articles: List[ArticleModel]) -> List[ArticleModel]:
        """
        Remove duplicate articles, keeping the best version of each story.

        Args:
            articles: List of articles to deduplicate

        Returns:
            Deduplicated list of articles
        """
        if not articles:
            return []

        self.duplicates_removed = 0
        self.duplicate_groups = []

        # Find duplicate groups
        groups = self._find_duplicates(articles)

        if not groups:
            logger.debug("No duplicates found")
            return articles

        # Track which articles to remove
        to_remove: Set[int] = set()

        for group_indices in groups:
            group_articles = [articles[i] for i in group_indices]
            duplicate_count = len(group_articles)

            # Log the duplicate group
            sources = [a.source_name for a in group_articles]
            logger.info(f"Duplicate story shared by {duplicate_count} sources: '{group_articles[0].title[:60]}...'")
            logger.debug(f"  Sources: {', '.join(sources)}")

            # Select best article and boost its importance
            best = self._select_best_article(group_articles, duplicate_count)
            self.duplicate_groups.append(group_articles)

            # Mark others for removal
            for i, article in zip(group_indices, group_articles):
                if article.id != best.id:
                    to_remove.add(i)
                    self.duplicates_removed += 1

        # Build result list
        result = [a for i, a in enumerate(articles) if i not in to_remove]

        logger.info(f"Deduplication: removed {self.duplicates_removed} duplicates, kept {len(result)}/{len(articles)}")

        return result

    def get_stats(self) -> Dict:
        """Get deduplication statistics"""
        return {
            "duplicates_removed": self.duplicates_removed,
            "duplicate_groups": len(self.duplicate_groups)
        }


# Global instance
content_deduplicator = ContentDeduplicator()
