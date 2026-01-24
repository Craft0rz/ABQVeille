# Installation de l'envoi automatique quotidien

Ce guide explique comment configurer l'envoi automatique du bulletin ABQ chaque matin à 7h00.

## Fichiers créés

- `run_daily_automated.bat` - Script batch pour l'exécution automatisée
- `ABQ_Daily_Task.xml` - Configuration du Planificateur de tâches Windows
- Ce guide d'installation

## Méthode 1: Importation automatique (RECOMMANDÉE)

### Étape 1: Importer la tâche planifiée

1. Ouvrir le **Planificateur de tâches** Windows:
   - Appuyez sur `Win + R`
   - Tapez `taskschd.msc`
   - Appuyez sur Entrée

2. Dans le panneau de droite, cliquez sur **"Importer une tâche..."**

3. Sélectionnez le fichier:
   ```
   c:\Users\mfont\projects\ABQ\ABQ_Daily_Task.xml
   ```

4. La fenêtre de configuration s'ouvre. Vérifiez:
   - **Nom**: ABQ_Daily_Task
   - **Déclencheur**: Tous les jours à 7:00 AM
   - **Action**: Exécute `run_daily_automated.bat`

5. Cliquez sur **OK** pour créer la tâche

### Étape 2: Vérifier les permissions

1. Dans le Planificateur de tâches, trouvez la tâche **ABQ_Daily_Task**
2. Faites un clic droit → **Propriétés**
3. Onglet **Général**:
   - ☑ Exécuter même si l'utilisateur n'est pas connecté (optionnel)
   - ☑ Exécuter avec les autorisations maximales (si nécessaire)

## Méthode 2: Configuration manuelle

Si l'importation XML ne fonctionne pas:

### Étape 1: Créer une nouvelle tâche

1. Ouvrir le Planificateur de tâches (`Win + R` → `taskschd.msc`)
2. Cliquez sur **"Créer une tâche..."** (pas "Créer une tâche de base")

### Étape 2: Onglet Général

- **Nom**: ABQ Daily Intelligence
- **Description**: Envoi quotidien du bulletin scientifique ABQ
- ☑ Exécuter même si l'utilisateur n'est pas connecté (optionnel)
- Configurer pour: Windows 10

### Étape 3: Onglet Déclencheurs

1. Cliquez sur **Nouveau...**
2. Configuration:
   - Lancer la tâche: **Selon une planification**
   - Paramètres: **Quotidien**
   - Tous les: **1 jour**
   - Démarrer: **07:00:00** (7h00 du matin)
   - ☑ Activé
3. Cliquez sur **OK**

### Étape 4: Onglet Actions

1. Cliquez sur **Nouveau...**
2. Configuration:
   - Action: **Démarrer un programme**
   - Programme/script:
     ```
     c:\Users\mfont\projects\ABQ\run_daily_automated.bat
     ```
   - Commencer dans (optionnel):
     ```
     c:\Users\mfont\projects\ABQ
     ```
3. Cliquez sur **OK**

### Étape 5: Onglet Conditions

- ☑ Démarrer la tâche uniquement si l'ordinateur est relié au secteur (désactiver si portable)
- ☑ Démarrer uniquement si la connexion réseau suivante est disponible: **N'importe quelle connexion**
- ☑ Réveiller l'ordinateur pour exécuter cette tâche (optionnel)

### Étape 6: Onglet Paramètres

- ☑ Autoriser l'exécution de la tâche à la demande
- ☑ Exécuter la tâche dès que possible si un démarrage planifié est manqué
- Si la tâche échoue, redémarrer toutes les: **5 minutes** (3 tentatives max)
- Arrêter la tâche si elle s'exécute plus de: **2 heures**

### Étape 7: Sauvegarder

Cliquez sur **OK** pour créer la tâche.

## Test de l'automatisation

### Test immédiat (recommandé)

Pour tester sans attendre 7h00:

1. Dans le Planificateur de tâches, trouvez la tâche **ABQ_Daily_Task**
2. Faites un clic droit → **Exécuter**
3. Vérifiez le fichier de log:
   ```
   c:\Users\mfont\projects\ABQ\logs\automated_run_YYYYMMDD.log
   ```

### Test via ligne de commande

Vous pouvez aussi exécuter directement:

```batch
cd c:\Users\mfont\projects\ABQ
run_daily_automated.bat
```

## Vérification des logs

Les logs d'exécution sont sauvegardés dans:
```
c:\Users\mfont\projects\ABQ\logs\
```

Format du nom: `automated_run_YYYYMMDD.log`

Exemple: `automated_run_20260124.log`

## Modifier l'heure d'exécution

Pour changer l'heure (par défaut 7h00):

1. Planificateur de tâches → Trouver **ABQ_Daily_Task**
2. Clic droit → **Propriétés**
3. Onglet **Déclencheurs** → Sélectionner le déclencheur → **Modifier**
4. Changer l'heure dans "Démarrer"
5. **OK** → **OK**

## Désactiver temporairement

Pour désactiver sans supprimer:

1. Planificateur de tâches → Trouver **ABQ_Daily_Task**
2. Clic droit → **Désactiver**

Pour réactiver: Clic droit → **Activer**

## Dépannage

### La tâche ne s'exécute pas

1. Vérifiez que l'ordinateur est allumé à 7h00
2. Vérifiez les paramètres "Conditions" (batterie, réseau)
3. Consultez l'historique: Clic droit sur la tâche → **Propriétés** → **Historique**

### Erreur d'exécution

1. Vérifiez le fichier log dans `logs/automated_run_YYYYMMDD.log`
2. Vérifiez que l'environnement virtuel existe: `c:\Users\mfont\projects\ABQ\.venv`
3. Testez manuellement: `run_daily_automated.bat`

### Pas de réception d'email

1. Vérifiez le log d'exécution
2. Vérifiez le fichier `.env`:
   - `ANTHROPIC_API_KEY` est défini
   - `RECIPIENT_EMAILS` contient votre email
3. Vérifiez `credentials/token.json` (authentification Gmail)

## Configuration actuelle

- **Heure d'exécution**: 7:00 AM (tous les jours)
- **Email destinataire**: mfontainegosselin@gmail.com (configuré dans `.env`)
- **Modèle AI**: claude-sonnet-4-20250514
- **Sources RSS**: 89 feeds actifs
- **Seuil de pertinence**: 0.02 (cible 5-20 articles/jour après filtrage AI)

## Support

En cas de problème:
1. Consultez les logs dans `logs/`
2. Testez l'exécution manuelle avec `run_daily.py`
3. Vérifiez la configuration dans `.env`
