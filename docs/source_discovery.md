# Système de Découverte Automatique de Sources ABQ

## Vue d'ensemble

Le système de découverte automatique analyse les articles existants pour identifier de nouvelles sources RSS pertinentes pour les biologistes québécois.

## Architecture

### Modules

1. **`source_analyzer.py`** - Analyse les articles pour extraire:
   - Domaines web mentionnés dans le contenu
   - Organisations citées (universités, instituts, ministères)
   - URLs de sources externes
   - Auteurs et leurs affiliations

2. **`feed_discovery.py`** - Découvre automatiquement les flux RSS:
   - Scan des chemins communs (`/rss`, `/feed`, `/atom.xml`)
   - Parsing HTML pour balises `<link rel="alternate">`
   - Validation des flux avec feedparser
   - Rate limiting pour éviter de surcharger les serveurs

3. **`discover_sources.py`** - Script principal orchestrant:
   - Analyse des articles existants
   - Découverte RSS sur domaines identifiés
   - Catégorisation automatique (research/environment/regulatory/general)
   - Génération de rapport avec nouvelles sources proposées

## Utilisation

### Mode analyse uniquement

Analyse les articles sans découvrir de nouveaux flux:

```bash
python discover_sources.py --analyze-only --min-mentions 2
```

**Résultats:**
- Liste des domaines fréquemment mentionnés
- Organisations identifiées (universités, centres de recherche)
- Arrêt après l'analyse (pas de scan RSS)

### Découverte complète

Lance le pipeline complet:

```bash
python discover_sources.py --min-mentions 3 --max-domains 10
```

**Paramètres:**
- `--min-mentions N`: Minimum de mentions pour considérer un domaine (défaut: 3)
- `--max-domains N`: Maximum de domaines à scanner (défaut: 20)

**Étapes:**
1. ✅ Analyse des articles (extraction domaines/organisations)
2. 🔍 Découverte RSS sur nouveaux domaines
3. 📋 Catégorisation automatique
4. 📄 Génération du rapport `data/discovered_sources.json`

### Résultats attendus

Le rapport `data/discovered_sources.json` contient:

```json
{
  "total": 5,
  "by_category": {
    "research": 3,
    "environment": 2
  },
  "sources": [
    {
      "name": "UdeM Nouvelles - Sciences",
      "url": "https://nouvelles.umontreal.ca/rss/sciences",
      "category": "research",
      "enabled": false,
      "priority": 1,
      "language": "fr",
      "_discovered": {
        "method": "html_link",
        "domain": "nouvelles.umontreal.ca",
        "discovery_date": "2026-01-25"
      }
    }
  ]
}
```

## Catégorisation automatique

Le système catégorise automatiquement selon:

### Categories

- **research**: Universités, centres de recherche, journaux scientifiques
- **regulatory**: Sites gouvernementaux (.gc.ca, .gouv.qc.ca)
- **environment**: Mots-clés environnement, écologie, conservation
- **general**: Autres sources

### Priorités

- **1**: Institutions québécoises (UQAM, UdeM, Laval, .qc.ca)
- **2**: Institutions canadiennes (McGill, Concordia, .ca)
- **3**: Sources internationales

### Langues

- **fr**: Domaines .qc.ca ou québécois
- **en**: Autres domaines

## Workflow recommandé

### 1. Analyse régulière (hebdomadaire)

```bash
# Analyser les nouvelles mentions
python discover_sources.py --min-mentions 2 --max-domains 15
```

### 2. Révision manuelle

Examiner `data/discovered_sources.json`:
- Vérifier la pertinence des sources
- Tester quelques articles du flux
- Valider la catégorie et priorité

### 3. Ajout manuel à feeds.json

Copier les sources validées dans `config/feeds.json`:

```json
{
  "name": "UdeM Nouvelles - Sciences",
  "url": "https://nouvelles.umontreal.ca/rss/sciences",
  "category": "research",
  "enabled": true,  // Activer après validation
  "priority": 1,
  "language": "fr"
}
```

### 4. Test des nouvelles sources

```bash
# Test avec le nouveau flux
python run_daily.py --test
```

## Patterns détectés

### Domaines typiques mentionnés

Les articles de sciences biologiques mentionnent souvent:

**Universités québécoises:**
- UQAM, UdeM, Laval, McGill, Concordia, UQTR, UQAC, UQAR
- ETS, Polytechnique, HEC, INRS

**Organismes de recherche:**
- INSPQ, INESSS, FRQ (FRQNT, FRQSC, FRQS)
- CRSNG/NSERC, Génome Québec, Mitacs

**Gouvernementaux:**
- MELCCFP, MFFP, MAPAQ
- Environnement et Changement climatique Canada

### Organisations extraites

Le système identifie automatiquement:
- `Université de [X]`
- `Centre de recherche [sur/en] [X]`
- `Institut [de] [X]`
- `Laboratoire [de] [X]`

## Limitations actuelles

### Domaines non québécois

Le système peut trouver des domaines internationaux mentionnés dans les articles scientifiques (WHO, EBI, UNHCR). Ces sources:
- Ne sont généralement pas pertinentes pour biologistes québécois
- Peuvent ne pas avoir de flux RSS en français
- Sont automatiquement déprioritisées (priority=3)

### RSS non détectable

Certains sites universitaires n'ont pas de flux RSS facilement détectable:
- Pages WordPress sans plugin RSS
- Sites avec RSS caché ou non standard
- Nécessite découverte manuelle

### Rate limiting

Le scan est limité à:
- 2 secondes entre chaque domaine (éviter surcharge)
- 10 secondes timeout par requête
- Maximum 20 domaines par défaut

## Améliorations futures

1. **Intégration AI**
   - Utiliser Claude pour suggérer sources similaires
   - Validation automatique de pertinence
   - Extraction intelligente de sources depuis contenu

2. **Base de données de sources**
   - Catalogue pré-rempli d'universités québécoises
   - URLs RSS connues pour institutions
   - Mapping domaine → RSS automatique

3. **Monitoring continu**
   - Vérification hebdomadaire automatique
   - Détection de nouveaux RSS sur sources existantes
   - Alerte si source devient inactive

4. **Validation automatique**
   - Test de pertinence des articles du flux
   - Score de qualité automatique
   - Recommandation d'activation/désactivation

## FAQ

**Q: Pourquoi si peu de nouvelles sources trouvées?**

R: Les articles analysés proviennent principalement de sources déjà dans feeds.json. Pour découvrir plus:
- Augmenter la période d'analyse (plus de jours de données)
- Réduire --min-mentions à 2
- Chercher manuellement dans les organisations identifiées

**Q: Comment ajouter manuellement une source québécoise?**

R: Si vous connaissez une université/organisation pertinente:
1. Visiter leur site web
2. Chercher "RSS", "Fil d'actualité", "Nouvelles"
3. Ajouter manuellement à feeds.json
4. Tester avec run_daily.py

**Q: Les sources sont désactivées par défaut?**

R: Oui (`enabled: false`). Toute nouvelle source nécessite:
- Validation manuelle du contenu
- Test de pertinence
- Activation explicite dans feeds.json

**Q: Comment prioriser les découvertes?**

R: Concentrer sur:
1. Universités québécoises (UQAM, UdeM, Laval, etc.)
2. Centres de recherche en biologie/écologie
3. Organismes gouvernementaux québécois (MELCCFP, INSPQ)
4. ONG environnementales québécoises

## Exemples d'utilisation

### Découvrir sources universitaires

```bash
# Analyse ciblée sur mentions universitaires
python discover_sources.py --min-mentions 2 --max-domains 30
```

### Audit complet

```bash
# Analyse sans limite (tous domaines)
python discover_sources.py --analyze-only --min-mentions 1
```

### Production (intégration CI/CD)

```bash
# Exécution hebdomadaire automatique
python discover_sources.py --min-mentions 5 --max-domains 10
# Puis notification si nouvelles sources > 0
```

## Support

Pour questions ou problèmes:
1. Vérifier les logs dans `logs/`
2. Consulter `data/discovered_sources.json`
3. Examiner les articles sources dans `data/YYYY-MM-DD/`
