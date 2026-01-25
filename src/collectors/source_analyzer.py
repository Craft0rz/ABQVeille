"""
Source Analyzer - Analyse les articles existants pour découvrir de nouvelles sources
"""
import json
import re
from typing import List, Dict, Set
from urllib.parse import urlparse
from collections import Counter
from pathlib import Path
from loguru import logger


class SourceAnalyzer:
    """Analyse les articles pour extraire domaines et organisations mentionnés"""

    def __init__(self):
        self.quebec_universities = [
            'uqam', 'umontreal', 'ulaval', 'mcgill', 'concordia', 'uqtr',
            'uqac', 'uqar', 'uqo', 'ets', 'polytechnique', 'hec', 'inrs'
        ]

        self.quebec_organizations = [
            'melccfp', 'mffp', 'mapaq', 'inspq', 'inesss',
            'frq', 'frqnt', 'frqsc', 'frqs', 'crsng', 'nserc',
            'genome quebec', 'mitacs'
        ]

        self.media_keywords = [
            'journal', 'presse', 'radio', 'nouvelles', 'actualit',
            'information', 'média', 'news'
        ]

    def analyze_articles_from_file(self, articles_file: Path) -> Dict:
        """Analyse un fichier d'articles pour extraire des patterns"""
        try:
            with open(articles_file, 'r', encoding='utf-8') as f:
                articles = json.load(f)

            return self.analyze_articles(articles)
        except Exception as e:
            logger.error(f"Error reading {articles_file}: {e}")
            return {}

    def analyze_articles(self, articles: List[Dict]) -> Dict:
        """Analyse une liste d'articles"""
        results = {
            'domains_mentioned': Counter(),
            'organizations_mentioned': Counter(),
            'urls_found': [],
            'authors': Counter(),
            'source_domains': Counter()
        }

        for article in articles:
            # Analyse du contenu
            text = self._get_article_text(article)

            # Extract URLs from content
            urls = self._extract_urls(text)
            for url in urls:
                domain = urlparse(url).netloc
                if domain and not self._is_excluded_domain(domain):
                    results['domains_mentioned'][domain] += 1
                    results['urls_found'].append(url)

            # Extract organizations
            orgs = self._extract_organizations(text)
            for org in orgs:
                results['organizations_mentioned'][org] += 1

            # Source domain
            if 'source_url' in article:
                source_domain = urlparse(article['source_url']).netloc
                results['source_domains'][source_domain] += 1

            # Authors (can indicate institutions)
            if article.get('author'):
                results['authors'][article['author']] += 1

        return results

    def _get_article_text(self, article: Dict) -> str:
        """Extrait tout le texte d'un article"""
        parts = []
        for field in ['title', 'summary', 'full_content', 'ai_summary']:
            if article.get(field):
                # Remove HTML tags
                text = re.sub(r'<[^>]+>', '', str(article[field]))
                parts.append(text)
        return ' '.join(parts)

    def _extract_urls(self, text: str) -> List[str]:
        """Extrait les URLs d'un texte"""
        # Pattern pour URLs
        url_pattern = r'https?://[^\s<>"{}|\\^`\[\]]+'
        urls = re.findall(url_pattern, text)
        return [url.rstrip('.,;:)') for url in urls]

    def _extract_organizations(self, text: str) -> List[str]:
        """Extrait les noms d'organisations du texte"""
        orgs = []
        text_lower = text.lower()

        # Check universities
        for uni in self.quebec_universities:
            if uni in text_lower:
                orgs.append(uni)

        # Check organizations
        for org in self.quebec_organizations:
            if org.lower() in text_lower:
                orgs.append(org)

        # Check for patterns like "Université de X", "Centre de recherche X"
        patterns = [
            r"université\s+(?:de\s+)?(\w+)",
            r"centre\s+de\s+recherche\s+(?:sur\s+)?(?:la\s+)?(\w+)",
            r"institut\s+(?:de\s+)?(\w+)",
            r"laboratoire\s+(?:de\s+)?(\w+)"
        ]

        for pattern in patterns:
            matches = re.finditer(pattern, text_lower)
            for match in matches:
                orgs.append(match.group(0))

        return orgs

    def _is_excluded_domain(self, domain: str) -> bool:
        """Vérifie si un domaine doit être exclu"""
        excluded = [
            'google.com', 'facebook.com', 'twitter.com', 'x.com',
            'youtube.com', 'linkedin.com', 'instagram.com',
            'doi.org', 'orcid.org'
        ]
        return any(excl in domain for excl in excluded)

    def find_potential_sources(self, data_dir: Path, min_mentions: int = 3) -> Dict:
        """Analyse tous les articles d'un répertoire de données"""
        logger.info(f"Analyzing articles in {data_dir}")

        all_results = {
            'domains_mentioned': Counter(),
            'organizations_mentioned': Counter(),
            'urls_found': [],
            'source_domains': Counter()
        }

        # Process all article files
        for articles_file in data_dir.glob('*/articles_*.json'):
            logger.info(f"Processing {articles_file}")
            results = self.analyze_articles_from_file(articles_file)

            # Merge results
            all_results['domains_mentioned'].update(results['domains_mentioned'])
            all_results['organizations_mentioned'].update(results['organizations_mentioned'])
            all_results['urls_found'].extend(results['urls_found'])
            all_results['source_domains'].update(results['source_domains'])

        # Filter by minimum mentions
        potential_sources = {
            'frequent_domains': {
                domain: count
                for domain, count in all_results['domains_mentioned'].most_common()
                if count >= min_mentions
            },
            'organizations': {
                org: count
                for org, count in all_results['organizations_mentioned'].most_common()
                if count >= min_mentions
            },
            'unique_urls': list(set(all_results['urls_found'])),
            'source_domains': dict(all_results['source_domains'])
        }

        logger.info(f"Found {len(potential_sources['frequent_domains'])} frequent domains")
        logger.info(f"Found {len(potential_sources['organizations'])} organizations")

        return potential_sources


if __name__ == "__main__":
    # Test
    from pathlib import Path

    analyzer = SourceAnalyzer()
    data_dir = Path(__file__).parent.parent.parent / 'data'

    results = analyzer.find_potential_sources(data_dir, min_mentions=2)

    print("\nDOMAINES FREQUEMMENT MENTIONNES:")
    for domain, count in sorted(results['frequent_domains'].items(), key=lambda x: x[1], reverse=True)[:20]:
        print(f"  {domain}: {count} mentions")

    print("\nORGANISATIONS MENTIONNEES:")
    for org, count in sorted(results['organizations'].items(), key=lambda x: x[1], reverse=True)[:20]:
        print(f"  {org}: {count} mentions")
