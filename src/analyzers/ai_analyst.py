"""
AI Analyst - Expert Article Analysis using Claude API

Analyzes relevant articles for biology/environment impact using Claude.
"""
from datetime import datetime
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
    logger.warning("anthropic package not installed - AI analysis disabled")


ARTICLE_ANALYSIS_PROMPT = """Vous etes un expert en communication scientifique pour les biologistes du Quebec.

DOMAINES D'EXPERTISE:
- Environnement et ecologie au Quebec et au Canada (changements climatiques, biodiversite, conservation, pollution, etudes d'impact)
- Reglementation environnementale quebecoise et canadienne (MELCCFP, Environnement et Changement climatique Canada)
- Recherche en biologie et sciences environnementales (universites, instituts)
- Politique environnementale et developpement durable

SECTEURS D'ACTIVITE DES BIOLOGISTES:
- Consultation environnementale et firmes d'experts
- Recherche et developpement (universites, instituts, entreprises)
- Secteur gouvernemental (provincial et federal)
- Education et enseignement
- Agroalimentaire et biotechnologie
- Sante et sciences biomedicales
- Conservation et gestion des ressources naturelles
- Aquaculture et pecheries
- Foresterie, faune et parcs

PRATIQUES SPECIALISEES EN ECOLOGIE APPLIQUEE:
- Caracterisations ecologiques et delimitations d'ecosystemes
- Milieux humides et habitats fauniques
- Inventaires fauniques et floristiques
- Especes a statut precaire et protocoles standardises
- Determination du statut des cours d'eau (criteres hydrologiques et ecologiques)
- Principe de precaution et approche scientifique multidisciplinaire

INSTITUTIONS CLES:
- Universites: UdeM, Laval, McGill, UQAM, UQAR, INRS, Sherbrooke
- Gouvernement: MELCCFP, MFFP, Environnement Canada, Parcs Canada
- Financement: FRQ, CRSNG, Genome Quebec

REGLES STRICTES ANTI-FABRICATION:
- Resumez UNIQUEMENT les informations EXPLICITEMENT mentionnees dans l'article.
- NE PAS inventer de chiffres, statistiques ou donnees qui ne sont pas dans l'article.
- NE PAS extrapoler l'impact sur les biologistes si l'article ne les mentionne pas directement.
- NE PAS quantifier un groupe (ex: "des milliers de biologistes") sans source dans l'article.
- Si l'article ne mentionne pas explicitement les biologistes ou leur domaine, dites simplement quel est le sujet de l'article et pourquoi il pourrait etre d'interet general, sans inventer un lien direct.
- Preferer "cet article pourrait interesser les biologistes car..." plutot que "cela affecte directement les biologistes".

Analysez cet article et repondez EXACTEMENT dans ce format (en francais):

RESUME:
[Resume en 2-3 phrases des FAITS rapportes dans l'article. Aucune interpretation, aucun ajout.]

IMPACT SCIENTIFIQUE:
[Si l'article mentionne explicitement les biologistes, l'ecologie ou un domaine connexe, decrivez le lien factuel. Sinon, indiquez simplement: "Article d'interet general pour la veille scientifique." NE PAS inventer de lien avec les biologistes qui n'existe pas dans l'article.]

NIVEAU D'IMPACT:
[Evaluez la pertinence pour les biologistes du Quebec. Choisissez EXACTEMENT UN mot:
- ELEVE: L'article mentionne explicitement un sujet directement lie au travail des biologistes au Quebec/Canada (reglementation environnementale, especes/ecosystemes, emplois en biologie, recherche universitaire en sciences naturelles, politiques environnementales)
- MOYEN: L'article traite d'un sujet en lien avec la biologie/environnement au Canada sans mentionner directement les biologistes (methodes scientifiques, recherche ecologique, enjeux climatiques mesurables, financement de la recherche scientifique)
- FAIBLE: Recherche internationale generale ou sujet peripherique - biologie fondamentale sans lien Quebec/Canada, especes/ecosystemes etrangers
- AUCUN: Hors sujet pour les biologistes. Ceci inclut:
  * Meteo, previsions meteorologiques (meme si "Environnement Canada" est la source)
  * Sport, divertissement, culture
  * Politique generale, elections, relations internationales, defense militaire
  * Finance, economie generale, bourse, tarifs douaniers
  * Securite publique, criminalite, faits divers
  * Agroalimentaire/alimentation SAUF si un aspect biologique/scientifique est central
  * Sante publique generale SAUF si epidemiologie ou microbiologie est le sujet central
  * Technologie non-scientifique

IMPORTANT: Soyez STRICT. Un article qui mentionne "Quebec" ou "Canada" n'est PAS automatiquement pertinent. Le sujet DOIT toucher la biologie, l'ecologie, l'environnement naturel, ou la recherche scientifique. En cas de doute, choisissez AUCUN plutot que FAIBLE.]

CATEGORIE D'IMPACT:
[Un de: recherche | politique | opportunite | environnement | carriere]"""


class AIAnalyst:
    """Expert science analyst using Claude API"""

    def __init__(self, model: Optional[str] = None, max_articles: Optional[int] = None):
        """
        Initialize AI Analyst.

        Args:
            model: Claude model to use (defaults to config setting)
            max_articles: Max articles to analyze (defaults to config setting)
        """
        self.model = model or config.ai.model
        self.enabled = config.ai.enabled and ANTHROPIC_AVAILABLE
        self.max_articles = max_articles or config.ai.max_articles_to_analyze
        self.temperature = config.ai.temperature

        if self.enabled:
            self.client = anthropic.Anthropic()
            logger.info(f"AIAnalyst initialized with model: {self.model}")
        else:
            self.client = None
            if not ANTHROPIC_AVAILABLE:
                logger.warning("AIAnalyst disabled: anthropic package not installed")
            elif not config.ai.enabled:
                logger.warning("AIAnalyst disabled: ANTHROPIC_API_KEY not set")

        # Stats
        self.stats = {
            "analyzed": 0,
            "failed": 0,
            "skipped": 0,
            "filtered_low_impact": 0
        }

    def analyze_article(self, article: ArticleModel) -> ArticleModel:
        """
        Analyze a single article for scientific impact.

        Args:
            article: Article to analyze

        Returns:
            Article with ai_summary, scientific_impact, and impact_category populated
        """
        if not self.enabled:
            self.stats["skipped"] += 1
            return article

        # Build article content for analysis
        content_parts = [f"TITLE: {article.title}"]

        if article.summary:
            content_parts.append(f"SUMMARY: {article.summary}")

        if article.full_content:
            # Truncate to avoid token limits
            content = article.full_content[:3000]
            content_parts.append(f"CONTENT: {content}")

        content_parts.append(f"SOURCE: {article.source_name}")
        content_parts.append(f"CATEGORY: {article.category}")

        if article.language:
            content_parts.append(f"LANGUAGE: {article.language}")

        if article.keywords_matched:
            content_parts.append(f"KEYWORDS MATCHED: {', '.join(article.keywords_matched)}")

        article_text = "\n\n".join(content_parts)

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=900,  # 500 cut off NIVEAU D'IMPACT on long analyses, silently dropping the article
                thinking={"type": "disabled"},  # Sonnet 5 defaults thinking ON; disable to keep max_tokens for output
                messages=[
                    {
                        "role": "user",
                        "content": f"{ARTICLE_ANALYSIS_PROMPT}\n\n---\n\nARTICLE TO ANALYZE:\n\n{article_text}"
                    }
                ]
            )

            # Parse response
            result = response.content[0].text

            if response.stop_reason == "max_tokens":
                # A cut-off response loses NIVEAU D'IMPACT, so the article is
                # silently filtered out of the digest. Make that visible.
                logger.warning(
                    f"Analysis hit max_tokens for '{article.title[:50]}...' - "
                    "impact level may be missing"
                )

            parsed = self._parse_analysis(result)

            article.ai_summary = parsed.get("summary")
            article.scientific_impact = parsed.get("scientific_impact")
            article.impact_category = parsed.get("impact_category")
            article.impact_level = parsed.get("impact_level")
            article.analyzed_at = datetime.now()

            self.stats["analyzed"] += 1
            logger.debug(f"Analyzed ({article.impact_level}): {article.title[:50]}...")

        except Exception as e:
            logger.error(f"Failed to analyze article '{article.title[:50]}...': {e}")
            self.stats["failed"] += 1

        return article

    def analyze_batch(self, articles: List[ArticleModel]) -> List[ArticleModel]:
        """
        Analyze multiple articles and filter out low-impact ones.

        Args:
            articles: List of articles to analyze

        Returns:
            List of articles with AI analysis populated, filtered to only ELEVE/MOYEN impact
        """
        if not self.enabled:
            logger.warning("AI analysis disabled - returning articles unchanged")
            return articles

        # Limit to max articles for cost control
        to_analyze = articles[:self.max_articles]

        logger.info(f"Analyzing {len(to_analyze)} articles (max: {self.max_articles})")

        analyzed = []
        for i, article in enumerate(to_analyze, 1):
            logger.info(f"Analyzing article {i}/{len(to_analyze)}: {article.title[:50]}...")
            analyzed.append(self.analyze_article(article))

        # Filter out only AUCUN impact articles (keep ELEVE, MOYEN, and FAIBLE)
        relevant_articles = []
        for article in analyzed:
            if article.impact_level in ("eleve", "moyen", "faible"):
                relevant_articles.append(article)
            else:
                self.stats["filtered_low_impact"] += 1
                logger.info(f"Filtered ({article.impact_level}): {article.title[:50]}...")

        logger.info(f"AI Analysis complete: {self.stats}")
        logger.info(f"Kept {len(relevant_articles)}/{len(analyzed)} articles with ELEVE/MOYEN/FAIBLE impact")

        # Only return relevant analyzed articles (excludes AUCUN)
        return relevant_articles

    def _parse_analysis(self, text: str) -> dict:
        """
        Parse Claude's analysis response (French format).

        Args:
            text: Raw response text

        Returns:
            Dict with summary, scientific_impact, impact_level, impact_category
        """
        result = {
            "summary": None,
            "scientific_impact": None,
            "impact_level": None,
            "impact_category": None
        }

        # Parse RESUME section (French)
        if "RESUME:" in text:
            start = text.find("RESUME:") + len("RESUME:")
            end = text.find("IMPACT SCIENTIFIQUE:")
            if end == -1:
                end = len(text)
            result["summary"] = text[start:end].strip()

        # Parse IMPACT SCIENTIFIQUE section (French)
        if "IMPACT SCIENTIFIQUE:" in text:
            start = text.find("IMPACT SCIENTIFIQUE:") + len("IMPACT SCIENTIFIQUE:")
            end = text.find("NIVEAU D'IMPACT:")
            if end == -1:
                end = text.find("CATEGORIE D'IMPACT:")
            if end == -1:
                end = len(text)
            result["scientific_impact"] = text[start:end].strip()

        # Parse NIVEAU D'IMPACT section (French)
        if "NIVEAU D'IMPACT:" in text:
            start = text.find("NIVEAU D'IMPACT:") + len("NIVEAU D'IMPACT:")
            end = text.find("CATEGORIE D'IMPACT:")
            if end == -1:
                end = len(text)
            level_text = text[start:end].strip().lower()
            # Map French levels to internal values
            level_map = {
                "eleve": "eleve",
                "élevé": "eleve",
                "moyen": "moyen",
                "faible": "faible",
                "aucun": "aucun"
            }
            for fr_level, internal_level in level_map.items():
                if fr_level in level_text:
                    result["impact_level"] = internal_level
                    break

        # Parse CATEGORIE D'IMPACT section (French)
        if "CATEGORIE D'IMPACT:" in text:
            start = text.find("CATEGORIE D'IMPACT:") + len("CATEGORIE D'IMPACT:")
            category = text[start:].strip().lower()
            # Map French categories to internal values
            category_map = {
                "recherche": "research",
                "politique": "policy",
                "opportunite": "opportunity",
                "environnement": "environment",
                "carriere": "career"
            }
            for fr_cat, en_cat in category_map.items():
                if fr_cat in category:
                    result["impact_category"] = en_cat
                    break

        return result

    def get_stats(self) -> dict:
        """Get analysis statistics"""
        return self.stats.copy()
