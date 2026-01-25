#!/usr/bin/env python3
"""
Discover Sources - Script automatisé pour découvrir de nouvelles sources RSS

Ce script:
1. Analyse les articles existants pour trouver des domaines/organisations mentionnés
2. Découvre automatiquement les flux RSS sur ces domaines
3. Utilise l'AI pour suggérer des sources similaires
4. Propose l'ajout automatique des nouvelles sources

Usage:
    python discover_sources.py [--analyze-only] [--min-mentions N] [--max-sources N]
"""
import argparse
import json
from pathlib import Path
from typing import List, Dict
from loguru import logger
import sys
import importlib.util

# Direct import of modules to avoid package issues
def import_module_from_path(module_name, file_path):
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

# Import modules directly
base_path = Path(__file__).parent / 'src' / 'collectors'
source_analyzer_module = import_module_from_path('source_analyzer', base_path / 'source_analyzer.py')
feed_discovery_module = import_module_from_path('feed_discovery', base_path / 'feed_discovery.py')

SourceAnalyzer = source_analyzer_module.SourceAnalyzer
FeedDiscovery = feed_discovery_module.FeedDiscovery


class SourceDiscoveryPipeline:
    """Pipeline automatisé de découverte de sources"""

    def __init__(self, config_path: Path, data_dir: Path):
        self.config_path = config_path
        self.data_dir = data_dir
        self.analyzer = SourceAnalyzer()
        self.discovery = FeedDiscovery()

        # Load existing feeds
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
            self.existing_feeds = config['feeds']
            self.existing_urls = {feed['url'] for feed in self.existing_feeds}
            self.existing_domains = {
                self._get_domain(feed['url']) for feed in self.existing_feeds
            }

    def _get_domain(self, url: str) -> str:
        """Extrait le domaine d'une URL"""
        from urllib.parse import urlparse
        return urlparse(url).netloc

    def step1_analyze_existing_articles(self, min_mentions: int = 3) -> Dict:
        """Étape 1: Analyse les articles existants"""
        logger.info("=" * 80)
        logger.info("ETAPE 1: Analyse des articles existants")
        logger.info("=" * 80)

        results = self.analyzer.find_potential_sources(self.data_dir, min_mentions)

        logger.info(f"Domaines fréquemment mentionnés: {len(results['frequent_domains'])}")
        logger.info(f"Organisations mentionnées: {len(results['organizations'])}")

        return results

    def _load_quebec_sources(self) -> List[str]:
        """Charge la liste prédéfinie de sources québécoises"""
        quebec_sources_path = self.config_path.parent / 'quebec_sources.json'

        if not quebec_sources_path.exists():
            logger.warning(f"Quebec sources file not found: {quebec_sources_path}")
            return []

        try:
            with open(quebec_sources_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # Extract all domains and sections
            domains_and_urls = []

            for category in ['universities', 'research_centers', 'government', 'media']:
                if category in data:
                    for org in data[category]:
                        # Add base domain
                        domains_and_urls.append(org['domain'])
                        # Add specific sections
                        for section in org.get('sections', []):
                            domains_and_urls.append(section)

            logger.info(f"Loaded {len(domains_and_urls)} Quebec sources from config")
            return domains_and_urls

        except Exception as e:
            logger.error(f"Error loading Quebec sources: {e}")
            return []

    def step2_discover_rss_feeds(self, domains: List[str], max_domains: int = 20, include_quebec_sources: bool = True) -> Dict:
        """Étape 2: Découvre les flux RSS sur les domaines mentionnés + sources québécoises prédéfinies"""
        logger.info("\n" + "=" * 80)
        logger.info("ETAPE 2: Découverte des flux RSS")
        logger.info("=" * 80)

        # Start with Quebec sources (priority)
        all_targets = []

        if include_quebec_sources:
            quebec_sources = self._load_quebec_sources()
            all_targets.extend(quebec_sources)
            logger.info(f"Ajouté {len(quebec_sources)} sources québécoises prédéfinies")

        # Add domains found in articles
        new_domains = [d for d in domains if d not in self.existing_domains]
        all_targets.extend(new_domains)

        # Remove duplicates while preserving order (Quebec sources first)
        seen = set()
        unique_targets = []
        for target in all_targets:
            # Extract domain from URL if needed
            if target.startswith('http'):
                from urllib.parse import urlparse
                domain = urlparse(target).netloc
            else:
                domain = target

            if domain not in seen and domain not in self.existing_domains:
                seen.add(domain)
                unique_targets.append(target)

        # Limit to max_domains
        targets_to_scan = unique_targets[:max_domains]

        logger.info(f"Scanning {len(targets_to_scan)} domaines/URLs ({len(quebec_sources) if include_quebec_sources else 0} québécois + {len(new_domains)} trouvés)")

        discovered = self.discovery.discover_from_domains(targets_to_scan, delay=2.0)

        logger.info(f"Flux RSS découverts sur {len(discovered)} domaines")

        return discovered

    def step3_categorize_and_validate(self, discovered_feeds: Dict) -> List[Dict]:
        """Étape 3: Catégorise et valide les nouvelles sources"""
        logger.info("\n" + "=" * 80)
        logger.info("ETAPE 3: Catégorisation et validation")
        logger.info("=" * 80)

        new_sources = []

        for domain, feeds in discovered_feeds.items():
            for feed in feeds:
                if feed['url'] in self.existing_urls:
                    continue

                # Auto-categorize based on domain/title
                category = self._auto_categorize(domain, feed['title'])
                priority = self._auto_prioritize(domain)
                language = self._detect_language(domain, feed['title'])

                new_source = {
                    'name': feed['title'],
                    'url': feed['url'],
                    'category': category,
                    'enabled': False,  # Disabled by default, needs manual review
                    'priority': priority,
                    'language': language,
                    '_discovered': {
                        'method': feed['method'],
                        'domain': domain,
                        'discovery_date': '2026-01-25'
                    }
                }

                new_sources.append(new_source)

        logger.info(f"Nouvelles sources validées: {len(new_sources)}")

        return new_sources

    def _auto_categorize(self, domain: str, title: str) -> str:
        """Catégorise automatiquement une source"""
        title_lower = title.lower()
        domain_lower = domain.lower()

        # Research indicators
        if any(kw in title_lower or kw in domain_lower for kw in [
            'université', 'university', 'recherche', 'research', 'plos',
            'journal', 'science', 'étude', 'laboratoire'
        ]):
            return 'research'

        # Regulatory indicators
        if any(kw in domain_lower for kw in [
            '.gc.ca', '.gouv', 'government', 'ministère', 'ministry'
        ]):
            return 'regulatory'

        # Environment indicators
        if any(kw in title_lower for kw in [
            'environnement', 'environment', 'écologie', 'ecology',
            'conservation', 'biodiversité', 'climat', 'nature'
        ]):
            return 'environment'

        # Default
        return 'general'

    def _auto_prioritize(self, domain: str) -> int:
        """Détermine automatiquement la priorité"""
        domain_lower = domain.lower()

        # Priority 1: Quebec institutions
        if any(kw in domain_lower for kw in [
            'uqam', 'umontreal', 'ulaval', '.qc.ca', 'quebec'
        ]):
            return 1

        # Priority 2: Canadian institutions
        if any(kw in domain_lower for kw in [
            '.ca', 'mcgill', 'concordia'
        ]):
            return 2

        # Priority 3: International
        return 3

    def _detect_language(self, domain: str, title: str) -> str:
        """Détecte la langue"""
        if '.qc.ca' in domain or 'quebec' in domain.lower():
            return 'fr'
        if any(kw in title.lower() for kw in ['québec', 'montréal', 'français']):
            return 'fr'
        return 'en'

    def step4_generate_report(self, new_sources: List[Dict]) -> None:
        """Étape 4: Génère un rapport des découvertes"""
        logger.info("\n" + "=" * 80)
        logger.info("ETAPE 4: Rapport de découverte")
        logger.info("=" * 80)

        # Group by category
        by_category = {}
        for source in new_sources:
            cat = source['category']
            if cat not in by_category:
                by_category[cat] = []
            by_category[cat].append(source)

        print("\n" + "=" * 80)
        print(f"NOUVELLES SOURCES DECOUVERTES: {len(new_sources)}")
        print("=" * 80)

        for category in sorted(by_category.keys()):
            sources = by_category[category]
            print(f"\n{category.upper()}: {len(sources)} sources")
            for src in sources[:10]:  # Show first 10
                print(f"  - {src['name']} ({src['language']})")
                print(f"    {src['url']}")
                print(f"    Priority: {src['priority']} | Method: {src['_discovered']['method']}")

        # Save report
        report_path = self.data_dir / 'discovered_sources.json'
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump({
                'total': len(new_sources),
                'by_category': {cat: len(srcs) for cat, srcs in by_category.items()},
                'sources': new_sources
            }, f, indent=2, ensure_ascii=False)

        print(f"\nRapport sauvegardé: {report_path}")

    def run(self, min_mentions: int = 3, max_domains: int = 20, analyze_only: bool = False):
        """Exécute le pipeline complet"""
        logger.info("Démarrage de la découverte automatique de sources")

        # Step 1: Analyze existing articles
        analysis = self.step1_analyze_existing_articles(min_mentions)

        if analyze_only:
            logger.info("Mode analyse uniquement - arrêt après l'analyse")
            return

        # Step 2: Discover RSS feeds
        domains = list(analysis['frequent_domains'].keys())
        discovered = self.step2_discover_rss_feeds(domains, max_domains)

        # Step 3: Categorize and validate
        new_sources = self.step3_categorize_and_validate(discovered)

        # Step 4: Generate report
        self.step4_generate_report(new_sources)

        logger.success(f"Découverte terminée! {len(new_sources)} nouvelles sources trouvées")


def main():
    parser = argparse.ArgumentParser(
        description="Discover new RSS sources automatically"
    )
    parser.add_argument(
        '--analyze-only',
        action='store_true',
        help='Only analyze existing articles without discovering new feeds'
    )
    parser.add_argument(
        '--min-mentions',
        type=int,
        default=3,
        help='Minimum mentions for a domain to be considered (default: 3)'
    )
    parser.add_argument(
        '--max-domains',
        type=int,
        default=20,
        help='Maximum number of domains to scan for RSS (default: 20)'
    )

    args = parser.parse_args()

    # Paths
    config_path = Path(__file__).parent / 'config' / 'feeds.json'
    data_dir = Path(__file__).parent / 'data'

    # Run pipeline
    pipeline = SourceDiscoveryPipeline(config_path, data_dir)
    pipeline.run(
        min_mentions=args.min_mentions,
        max_domains=args.max_domains,
        analyze_only=args.analyze_only
    )


if __name__ == "__main__":
    main()
