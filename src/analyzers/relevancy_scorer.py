"""
Relevancy Scorer

Scores articles for ABQ (Association des Biologistes du Quebec) relevancy
using weighted keyword matching with comprehensive biology and environment tracking.
"""
import re
import unicodedata
from typing import List, Set, Dict, Optional, Union
from loguru import logger

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from ABQ.src.models.article import ArticleModel
from ABQ.src.config import config


class RelevancyScorer:
    """Scores articles for ABQ biology relevancy"""

    # Location weights for keyword matches
    WEIGHTS = {
        "title": 3.0,      # Title matches most important
        "summary": 1.5,    # Summary matches moderately important
        "tags": 1.5,       # Tags moderately important
        "full_content": 1.0  # Content baseline
    }

    # ABQ and related organization names (highest priority)
    ORGANIZATION_NAMES = {
        "abq", "association des biologistes", "biologistes du quebec",
        "ordre des biologistes", "obq"
    }

    # Quebec universities and research institutions
    QUEBEC_INSTITUTIONS = {
        # Universities
        "uqam", "universite du quebec", "udem", "universite de montreal",
        "laval", "universite laval", "mcgill", "concordia", "sherbrooke",
        "uqar", "uqac", "uqat", "uqo", "uqtr", "ets", "teluq",
        # Research centers
        "inrs", "ircm", "crchum", "chum", "cusm", "muhc",
        "jardin botanique", "biodome", "insectarium",
        "centre de la science", "cosepac", "cosewic"
    }

    # Funding organizations
    FUNDING_ORGS = {
        # Quebec
        "frq", "frqs", "frqnt", "frqsc", "fonds de recherche",
        "mitacs", "genome quebec", "genomique quebec",
        # Federal
        "nserc", "crsng", "cihr", "irsc", "sshrc", "crsh",
        "conseil de recherches", "research council"
    }

    # Biology disciplines - French
    BIOLOGY_FR = {
        "biologie", "biologiste", "biochimie", "biochimiste",
        "microbiologie", "microbiologiste", "genetique", "geneticien",
        "genomique", "proteomique", "bioinformatique", "biotechnologie",
        "sciences de la vie", "sciences naturelles", "sciences biologiques",
        "ecologie", "ecologue", "ecologiste", "taxonomie", "taxonomiste",
        "entomologie", "entomologiste", "ornithologie", "ornithologue",
        "ichtyologie", "ichtyologiste", "mammalogie", "mammalogiste",
        "herpetologie", "herpetologiste", "mycologie", "mycologue",
        "botanique", "botaniste", "phycologie", "phycologue",
        "limnologie", "limnologue", "oceanographie", "oceanographe",
        "physiologie", "physiologiste", "neurobiologie", "neurobiologiste",
        "biologie moleculaire", "biologie cellulaire", "biologie marine",
        "biologie vegetale", "biologie animale", "parasitologie",
        "immunologie", "virologie", "bacteriologie", "toxicologie",
        "pharmacologie", "epidemiologie", "biostatistique"
    }

    # Biology disciplines - English
    BIOLOGY_EN = {
        "biology", "biologist", "biochemistry", "biochemist",
        "microbiology", "microbiologist", "genetics", "geneticist",
        "genomics", "proteomics", "bioinformatics", "biotechnology",
        "life sciences", "natural sciences", "biological sciences",
        "ecology", "ecologist", "taxonomy", "taxonomist",
        "entomology", "entomologist", "ornithology", "ornithologist",
        "ichthyology", "ichthyologist", "mammalogy", "mammalogist",
        "herpetology", "herpetologist", "mycology", "mycologist",
        "botany", "botanist", "phycology", "phycologist",
        "limnology", "limnologist", "oceanography", "oceanographer",
        "physiology", "physiologist", "neurobiology", "neurobiologist",
        "molecular biology", "cell biology", "marine biology",
        "plant biology", "animal biology", "parasitology",
        "immunology", "virology", "bacteriology", "toxicology",
        "pharmacology", "epidemiology", "biostatistics"
    }

    # Environment keywords - French
    ENVIRONMENT_FR = {
        # General environment
        "environnement", "environnemental", "ecologie", "ecosysteme",
        "biodiversite", "conservation", "habitat", "faune", "flore",
        "especes menacees", "especes en peril", "especes invasives",
        "espece a statut precaire", "statut precaire",
        "changement climatique", "rechauffement climatique", "climat",
        "pollution", "contaminants", "decontamination", "remediation",
        "developpement durable", "durabilite", "empreinte carbone",
        "gaz a effet de serre", "ges", "carbone", "sequestration",
        # Forests and parks
        "foret", "foret boreale", "foresterie", "reboisement",
        "parcs nationaux", "parcs quebec", "sepaq", "reserves naturelles",
        "aires protegees", "zone sensible",
        # Wetlands and aquatic
        "milieux humides", "marecages", "tourbieres", "wetlands",
        "fleuve saint-laurent", "grands lacs", "lac", "riviere",
        "eau douce", "eau salee", "aquatique", "marine",
        "cours d'eau", "ecoulement", "hydrologie", "bassin versant",
        # Applied ecology practices
        "caracterisation ecologique", "delimitation ecosysteme",
        "inventaire faunique", "inventaire floristique",
        "habitat faunique", "protocole standardise",
        "etude impact", "etude environnementale", "evaluation environnementale",
        "restauration ecologique", "renaturalisation",
        # Specific sectors
        "aquaculture", "pecheries", "peche",
        "gestion ressources naturelles", "amenagement territoire"
    }

    # Environment keywords - English
    ENVIRONMENT_EN = {
        "environment", "environmental", "ecology", "ecosystem",
        "biodiversity", "conservation", "habitat", "wildlife", "flora",
        "endangered species", "species at risk", "invasive species",
        "climate change", "global warming", "climate",
        "pollution", "contaminants", "decontamination", "remediation",
        "sustainable development", "sustainability", "carbon footprint",
        "greenhouse gas", "ghg", "carbon", "sequestration",
        "forest", "boreal forest", "forestry", "reforestation",
        "wetlands", "marshes", "peatlands", "bogs",
        "st lawrence river", "great lakes", "lake", "river",
        "freshwater", "saltwater", "aquatic", "marine",
        "protected areas", "national parks", "nature reserves",
        "ecological restoration", "rewilding"
    }

    # Regulatory keywords - French
    REGULATORY_FR = {
        # General regulatory
        "reglementation", "legislation", "loi", "reglement",
        "politique environnementale", "politique publique",
        "permis", "autorisation", "certification", "conformite",
        "normes environnementales",
        # Quebec government
        "ministere environnement", "melcc", "melccfp",
        "mffp", "ministere forets faune parcs",
        "bape", "bureau audiences publiques",
        # Federal government
        "environnement canada", "eccc",
        "environnement et changement climatique canada",
        "parcs canada", "peches et oceans", "mpo",
        "agence evaluation impact",
        # Assessment
        "evaluation environnementale", "etude impact",
        "principe precaution", "approche scientifique",
        "criteres hydrologiques", "criteres ecologiques",
        # Professional associations
        "agrcq", "ordre des biologistes"
    }

    # Regulatory keywords - English
    REGULATORY_EN = {
        "regulation", "legislation", "law", "policy",
        "environment ministry", "environment canada", "parks canada",
        "environmental assessment", "impact study",
        "permit", "authorization", "certification",
        "environmental standards", "compliance"
    }

    # Research keywords - French
    RESEARCH_FR = {
        "recherche", "recherche scientifique", "etude", "publication",
        "decouverte", "innovation", "experience", "laboratoire",
        "these", "doctorat", "maitrise", "postdoctorat",
        "subvention", "bourse", "financement", "projet de recherche",
        "revue scientifique", "article scientifique", "peer review"
    }

    # Professional sectors - French (where biologists work)
    SECTORS_FR = {
        # Consultation
        "consultation environnementale", "consultant", "firme",
        "bureau etudes", "expertise environnementale",
        # R&D
        "recherche developpement", "r&d", "centre recherche",
        # Government
        "fonction publique", "gouvernement", "provincial", "federal",
        "ministere", "agence gouvernementale",
        # Education
        "enseignement", "education", "professeur", "formation",
        # Agri-food and biotech
        "agroalimentaire", "agriculture", "biotechnologie",
        "biopharma", "pharmaceutique",
        # Health
        "sante", "biomedicale", "sciences biomedicales",
        # Conservation
        "organisme conservation", "ong environnement",
        "protection nature", "fondation"
    }

    # Research keywords - English
    RESEARCH_EN = {
        "research", "scientific research", "study", "publication",
        "discovery", "innovation", "experiment", "laboratory",
        "thesis", "doctorate", "masters", "postdoctoral",
        "grant", "scholarship", "funding", "research project",
        "scientific journal", "scientific article", "peer review"
    }

    # Quebec-specific terms (highest priority)
    QUEBEC_SPECIFIC = {
        "quebec", "quebecois", "montreal", "laval", "gatineau", "sherbrooke",
        "nord du quebec", "cote nord", "saguenay", "lac saint jean",
        "gaspesie", "bas saint laurent", "charlevoix", "laurentides",
        "outaouais", "abitibi", "temiscamingue", "mauricie",
        "estrie", "monteregie", "lanaudiere", "chaudiere appalaches",
        "ile anticosti", "iles de la madeleine", "ile d'orleans"
    }

    # Canada-specific terms (medium priority)
    CANADA_SPECIFIC = {
        "canada", "canadien", "canadian", "ontario", "colombie britannique",
        "british columbia", "alberta", "saskatchewan", "manitoba",
        "nouveau brunswick", "new brunswick", "nouvelle ecosse", "nova scotia",
        "terre neuve", "newfoundland", "ile du prince edouard", "prince edward island",
        "yukon", "territoires du nord ouest", "northwest territories", "nunavut",
        "toronto", "vancouver", "calgary", "ottawa", "edmonton", "winnipeg",
        "halifax", "victoria"
    }

    # All keywords combined by type
    ALL_ORGANIZATIONS = ORGANIZATION_NAMES | QUEBEC_INSTITUTIONS | FUNDING_ORGS
    ALL_BIOLOGY = BIOLOGY_FR | BIOLOGY_EN
    ALL_ENVIRONMENT = ENVIRONMENT_FR | ENVIRONMENT_EN
    ALL_REGULATORY = REGULATORY_FR | REGULATORY_EN
    ALL_RESEARCH = RESEARCH_FR | RESEARCH_EN
    ALL_SECTORS = SECTORS_FR
    ALL_LOCATION = QUEBEC_SPECIFIC | CANADA_SPECIFIC

    # Priority thresholds
    HIGH_THRESHOLD = 0.6
    MEDIUM_THRESHOLD = 0.3

    def __init__(self):
        """Initialize scorer with comprehensive keywords"""
        # Combine all keyword sets
        self.keywords = (
            self.ALL_BIOLOGY | self.ALL_ENVIRONMENT |
            self.ALL_REGULATORY | self.ALL_RESEARCH |
            self.ALL_SECTORS | self.ALL_LOCATION
        )
        self.min_score = config.analysis.min_relevancy_score
        self.max_per_category = config.analysis.max_articles_per_category

        logger.info(
            f"RelevancyScorer initialized: {len(self.keywords)} keywords, "
            f"{len(self.ALL_ORGANIZATIONS)} organizations tracked"
        )

    def _get_text_for_field(self, article: ArticleModel, field: str) -> str:
        """Get text content for a specific field"""
        if field == "title":
            return article.title or ""
        elif field == "summary":
            return article.summary or ""
        elif field == "tags":
            return " ".join(article.tags) if article.tags else ""
        elif field == "full_content":
            return article.full_content or ""
        return ""

    def _normalize_text(self, text: str) -> str:
        """
        Normalize text for matching: lowercase and remove accents.

        This ensures "Québec" matches "quebec", "Montréal" matches "montreal", etc.
        """
        # Lowercase
        text = text.lower()
        # Remove accents: NFD decomposes é -> e + ´, then we keep only non-marks
        text = unicodedata.normalize('NFD', text)
        text = ''.join(c for c in text if unicodedata.category(c) != 'Mn')
        return text

    def _find_matches(self, text: str, keywords: Union[set, list]) -> Set[str]:
        """
        Find all keyword matches in text (case-insensitive, accent-insensitive).

        Both text and keywords are normalized to remove accents before matching,
        so "Québec" will match "quebec" keyword.
        """
        text_normalized = self._normalize_text(text)
        matches = set()
        for keyword in keywords:
            # Normalize keyword too
            keyword_normalized = self._normalize_text(keyword)
            # Use word boundary matching for better precision
            pattern = r'\b' + re.escape(keyword_normalized) + r'\b'
            if re.search(pattern, text_normalized):
                matches.add(keyword)  # Return original keyword (not normalized)
        return matches

    def _find_organization_mentions(self, text: str) -> Set[str]:
        """Find organization mentions in text"""
        return self._find_matches(text, self.ALL_ORGANIZATIONS)

    def _has_abq_mention(self, text: str) -> bool:
        """Check if text contains ABQ/organization mentions (accent-insensitive)"""
        text_normalized = self._normalize_text(text)
        return any(self._normalize_text(name) in text_normalized for name in self.ORGANIZATION_NAMES)

    def _categorize_matches(self, matches: Set[str]) -> Dict[str, Set[str]]:
        """Categorize matches by type for better analysis"""
        categories = {
            "biology": matches & self.ALL_BIOLOGY,
            "environment": matches & self.ALL_ENVIRONMENT,
            "regulatory": matches & self.ALL_REGULATORY,
            "research": matches & self.ALL_RESEARCH,
            "quebec": matches & self.QUEBEC_SPECIFIC,
            "organizations": matches & self.ALL_ORGANIZATIONS
        }
        return {k: v for k, v in categories.items() if v}

    def score_article(self, article: ArticleModel) -> ArticleModel:
        """
        Calculate relevancy score and update article.

        Args:
            article: ArticleModel to score

        Returns:
            Updated article with relevancy_score, keywords_matched, priority
        """
        all_matches: Set[str] = set()
        org_matches: Set[str] = set()
        weighted_score = 0.0

        # Collect all text
        all_text = " ".join([
            article.title or "",
            article.summary or "",
            article.full_content or ""
        ])

        # Check each field for keyword matches
        for field, weight in self.WEIGHTS.items():
            text = self._get_text_for_field(article, field)
            if not text:
                continue

            # Find keyword matches
            matches = self._find_matches(text, self.keywords)
            all_matches.update(matches)
            weighted_score += len(matches) * weight

            # Find organization mentions (extra weight)
            org_match = self._find_organization_mentions(text)
            org_matches.update(org_match)
            # Organizations get 1.5x weight
            weighted_score += len(org_match) * weight * 1.5

        # Apply ABQ mention boost (50% boost)
        if self._has_abq_mention(all_text):
            weighted_score *= 1.5

        # Apply location-based boosts (hierarchical priority: Quebec > Canada > International)
        quebec_matches = self._find_matches(all_text, self.QUEBEC_SPECIFIC)
        canada_matches = self._find_matches(all_text, self.CANADA_SPECIFIC)

        if quebec_matches:
            # Quebec content: 50% boost (highest priority)
            weighted_score *= 1.5
        elif canada_matches:
            # Canada content (non-Quebec): 25% boost (medium priority)
            weighted_score *= 1.25

        # Apply French content boost (10% for French sources - prioritize local content)
        if article.language == "fr":
            weighted_score *= 1.1

        # Normalize score to 0.0-1.0 range
        max_possible = 80.0
        normalized = min(1.0, weighted_score / max_possible)

        # Combine all matched terms
        all_matched = all_matches | org_matches

        # Update article fields
        article.relevancy_score = round(normalized, 3)
        article.keywords_matched = sorted(list(all_matched))
        article.priority = self._assign_priority(normalized)

        return article

    def _assign_priority(self, score: float) -> int:
        """Assign priority based on score"""
        if score >= self.HIGH_THRESHOLD:
            return 1  # HIGH
        elif score >= self.MEDIUM_THRESHOLD:
            return 2  # MEDIUM
        return 3  # LOW

    def score_batch(self, articles: List[ArticleModel]) -> List[ArticleModel]:
        """
        Score multiple articles and return sorted by relevancy.

        Args:
            articles: List of articles to score

        Returns:
            Scored articles sorted by relevancy_score descending
        """
        logger.info(f"Scoring {len(articles)} articles")

        scored = [self.score_article(article) for article in articles]

        # Sort by score (highest first)
        scored.sort(key=lambda a: a.relevancy_score, reverse=True)

        # Log distribution
        high = sum(1 for a in scored if a.priority == 1)
        medium = sum(1 for a in scored if a.priority == 2)
        low = sum(1 for a in scored if a.priority == 3)
        logger.info(f"Priority distribution: HIGH={high}, MEDIUM={medium}, LOW={low}")

        # Log organization mentions
        org_articles = [
            a for a in scored
            if a.keywords_matched and any(c in a.keywords_matched for c in self.ALL_ORGANIZATIONS)
        ]
        if org_articles:
            logger.info(f"Articles with organization mentions: {len(org_articles)}")

        return scored

    # International sources that require Quebec keywords
    INTERNATIONAL_SOURCES = {
        'plos one', 'plos biology', 'plos genetics', 'plos pathogens',
        'nature', 'science', 'cell', 'lancet', 'biorxiv', 'arxiv'
    }

    def filter_relevant(self, articles: List[ArticleModel]) -> List[ArticleModel]:
        """
        Return only articles meeting minimum relevancy threshold.

        Filtering rules:
        - General category: must have biology/environment/research keywords
        - International sources (PLOS, etc.): must have Quebec keywords
        - All articles: must meet min_relevancy_score threshold

        Args:
            articles: List of scored articles

        Returns:
            Filtered list above min_relevancy_score
        """
        relevant = []
        general_filtered = 0
        international_filtered = 0

        for article in articles:
            if article.relevancy_score < self.min_score:
                continue

            matched = set(article.keywords_matched) if article.keywords_matched else set()

            # Filter international sources (PLOS and similar)
            # Require at least one Quebec-specific keyword
            source_lower = article.source_name.lower()
            is_international = any(intl in source_lower for intl in self.INTERNATIONAL_SOURCES)

            if is_international:
                has_quebec = bool(matched & self.QUEBEC_SPECIFIC)
                if not has_quebec:
                    international_filtered += 1
                    logger.debug(
                        f"Filtered international source (no QC keywords): "
                        f"{article.source_name} - {article.title[:50]}..."
                    )
                    continue

            # Stricter filter for general category
            if article.category == "general":
                # General articles must match biology, environment, or organization keywords
                # Location-only (quebec, canada, montreal) and sector-only (gouvernement,
                # financement, sante, education) matches are NOT sufficient — these match
                # any Quebec news and let irrelevant articles through.
                has_biology = bool(matched & self.ALL_BIOLOGY)
                has_org = bool(matched & self.ALL_ORGANIZATIONS)

                # For environment, exclude generic terms that match non-science news
                GENERIC_ENV_TERMS = {
                    "environnement", "environment", "climat", "climate",
                    "pollution", "sante", "health"
                }
                env_matches = matched & self.ALL_ENVIRONMENT
                specific_env = env_matches - GENERIC_ENV_TERMS
                # Require at least one specific environment keyword, or 2+ generic ones
                # (single "environnement" from weather reports is not enough)
                has_specific_environment = bool(specific_env) or len(env_matches) >= 2

                # For research, exclude generic terms
                GENERIC_RESEARCH_TERMS = {
                    "etude", "study", "publication", "laboratoire", "laboratory",
                    "financement", "funding", "bourse", "scholarship",
                    "formation", "innovation", "experience"
                }
                research_matches = matched & self.ALL_RESEARCH
                specific_research = research_matches - GENERIC_RESEARCH_TERMS
                has_specific_research = bool(specific_research)

                # General articles must have at least one strong signal
                if not (has_biology or has_specific_environment or has_specific_research or has_org):
                    general_filtered += 1
                    continue

                # General articles need higher score threshold
                if article.relevancy_score < 0.15:
                    general_filtered += 1
                    continue

            relevant.append(article)

        logger.info(
            f"Filtered to {len(relevant)}/{len(articles)} relevant articles "
            f"(threshold: {self.min_score}, general filtered: {general_filtered}, "
            f"international filtered: {international_filtered})"
        )
        return relevant

    def get_top_per_category(
        self,
        articles: List[ArticleModel],
        n: Optional[int] = None
    ) -> Dict[str, List[ArticleModel]]:
        """
        Get top N articles per category.

        Args:
            articles: List of scored articles
            n: Number per category (default from config)

        Returns:
            Dict mapping category to top articles
        """
        n = n or self.max_per_category
        by_category: Dict[str, List[ArticleModel]] = {}

        for article in articles:
            cat = article.category
            if cat not in by_category:
                by_category[cat] = []
            if len(by_category[cat]) < n:
                by_category[cat].append(article)

        return by_category


# Convenience function
def score_articles(articles: List[ArticleModel]) -> List[ArticleModel]:
    """Score and sort articles by relevancy"""
    scorer = RelevancyScorer()
    return scorer.score_batch(articles)
