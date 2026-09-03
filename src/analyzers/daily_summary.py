"""
Daily Summary Generator - Executive Brief using Claude API

Generates a daily executive summary synthesizing all relevant news.
"""
from typing import List, Optional
from loguru import logger

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from ABQ.src.models.article import ArticleModel
from ABQ.src.config import config

try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False


DAILY_SUMMARY_PROMPT = """You are writing a factual brief for the Association des Biologistes du Quebec (ABQ) members.

TASK: Summarize today's science and environment news as a SHORT BULLET LIST (3-5 bullets max) in French. Each bullet corresponds to ONE article — do NOT merge or connect unrelated articles.

SELECTION: the articles below are pre-ranked, most important first (impact level, then relevancy). Cover the TOP stories, in that order. Leaving the lower-ranked articles out is expected and correct - never drop a top story to make room for a minor one.

STRICT RULES:
- Each claim must come from a specific article. Do not invent connections between articles.
- Report ONLY facts stated in the articles. Never extrapolate, speculate, or infer consequences not mentioned.
- Do NOT quantify impacts on biologists unless the article provides specific data (e.g., never say "des milliers de biologistes" unless the article says so).
- Do NOT claim an article "threatens" or "directly affects" biologists unless the article explicitly says so.
- If an article is about a general topic (immigration policy, demographics, weather), summarize what the article actually says — do not invent a link to biology.
- Name sources and institutions only when the article mentions them.
- Write in French (the official language of ABQ).
- Prefer factual summaries over dramatic narratives. Accuracy > impact.

FORMAT: Return ONLY the bullets, one per line, each starting with "- " (hyphen + space). No introduction, no conclusion, no headers.

LENGTH (strict): each bullet is ONE sentence of 200 characters maximum. Do NOT chain several facts with semicolons or "et" - keep the single most important fact of the article and drop the rest. A short complete bullet is always better than a long one.

BAD:
- "La crise migratoire plonge des milliers de biologistes dans l'incertitude, menacant la recherche publique."
(Invents numbers, fabricates causal links, speculates on consequences.)

GOOD:
- Le MELCCFP publie de nouvelles lignes directrices sur les milieux humides touchant les evaluations environnementales.
- Une etude de l'Universite Laval documente un declin de 12% des populations de caribou dans le nord du Quebec.
(Each bullet = one article, only facts from the article, no invented connections.)

Keep it tight and factual. Scientists value accuracy above all."""


class DailySummaryGenerator:
    """Generates executive daily summary from analyzed articles"""

    # Ordering used to decide which stories earn one of the few bullets.
    IMPACT_RANK = {"eleve": 0, "moyen": 1, "faible": 2}

    def __init__(self, model: Optional[str] = None):
        """
        Initialize Daily Summary Generator.

        Args:
            model: Claude model to use (defaults to config setting)
        """
        self.model = model or config.ai.model
        self.enabled = config.ai.enabled and ANTHROPIC_AVAILABLE
        self.temperature = config.ai.temperature

        if self.enabled:
            self.client = anthropic.Anthropic()
            logger.info(f"DailySummaryGenerator initialized with model: {self.model}")
        else:
            self.client = None

    @staticmethod
    def _drop_incomplete_bullets(summary: str) -> str:
        """
        Drop trailing bullets that were cut off mid-sentence.

        The model is capped by max_tokens, so the last bullet can end mid-word.
        Members read this section first - a dangling fragment reads as a bug.
        Better to send one bullet fewer than one broken one.

        Args:
            summary: Raw summary text, one bullet per line

        Returns:
            Summary with incomplete trailing bullets removed (original text if
            that would leave nothing to send)
        """
        lines = [line for line in summary.strip().splitlines() if line.strip()]

        while lines and not lines[-1].rstrip().endswith((".", "!", "?", "…", '"', ")")):
            dropped = lines.pop()
            logger.warning(f"Dropped truncated bullet: ...{dropped.strip()[-60:]}")

        if not lines:
            logger.error("All bullets looked truncated - sending summary as-is")
            return summary.strip()

        return "\n".join(lines)

    def generate(self, articles: List[ArticleModel], date_str: str) -> Optional[str]:
        """
        Generate executive summary from analyzed articles.

        Args:
            articles: List of analyzed articles
            date_str: Date string (YYYY-MM-DD)

        Returns:
            Executive summary text, or None if disabled/failed
        """
        if not self.enabled:
            logger.warning("Daily summary generation disabled - no API key")
            return None

        if not articles:
            logger.warning("No articles to summarize")
            return None

        # The rest of the email ranks by relevancy; the summary must too, or the
        # bullets that survive the 3-5 cap are just whatever arrived first.
        ranked = sorted(
            articles,
            key=lambda a: (
                self.IMPACT_RANK.get(a.impact_level, len(self.IMPACT_RANK)),
                -(a.relevancy_score or 0.0),
            ),
        )

        # Build article summaries for the prompt
        article_summaries = []
        for i, article in enumerate(ranked, 1):
            parts = [f"{i}. {article.title}"]
            parts.append(f"   Source: {article.source_name} | Category: {article.category}")

            if article.impact_level:
                parts.append(f"   Impact Level: {article.impact_level}")

            if article.language:
                parts.append(f"   Language: {article.language}")

            if article.ai_summary:
                parts.append(f"   Summary: {article.ai_summary}")
            elif article.summary:
                parts.append(f"   Summary: {article.summary[:200]}...")

            if article.scientific_impact:
                parts.append(f"   Scientific Impact: {article.scientific_impact}")

            if article.impact_category:
                parts.append(f"   Impact Type: {article.impact_category}")

            article_summaries.append("\n".join(parts))

        articles_text = "\n\n".join(article_summaries)

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=1200,  # 300 truncated 2 of 3 summaries mid-sentence after the Sonnet 5 migration
                thinking={"type": "disabled"},  # Sonnet 5 defaults thinking ON; disable to keep max_tokens for output
                messages=[
                    {
                        "role": "user",
                        "content": f"{DAILY_SUMMARY_PROMPT}\n\n---\n\nDATE: {date_str}\nARTICLES ({len(articles)} total):\n\n{articles_text}"
                    }
                ]
            )

            summary = response.content[0].text

            if response.stop_reason == "max_tokens":
                logger.warning(
                    f"Daily summary hit max_tokens ({len(summary)} chars) - "
                    "trailing bullet is incomplete, consider raising the budget"
                )

            summary = self._drop_incomplete_bullets(summary)
            logger.info(f"Generated daily summary: {len(summary)} chars")
            return summary

        except Exception as e:
            logger.error(f"Failed to generate daily summary: {e}")
            return None
