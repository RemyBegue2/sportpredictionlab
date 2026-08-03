# Mise à niveau V3.9 sans Python local

## Objectif

Corriger les ratios de couverture du lot V3.8 et recalculer le dernier artefact historique sans nouvel appel The Odds API.

## 1. Copier l’upgrade dans GitHub

Décompressez l’archive V3.9. Les dossiers suivants doivent apparaître directement à sa racine :

```text
.github/
scripts/
sports_predictor/
static/
tests/
```

Copiez leur contenu à la racine du dépôt et acceptez les remplacements.

Ne remplacez pas et ne supprimez pas :

```text
artifacts/football_model.joblib
artifacts/tennis_model.joblib
artifacts/metrics.json
artifacts/artifact_manifest.json
artifacts/fresh_rebuild_report.json
data/real/
```

Créez le commit :

```text
Upgrade to V3.9 data reliability
```

## 2. Mettre à jour Railway

Sur les services `sportpredictionlab` et `shadow-cron`, définissez :

```text
MODEL_VERSION=3.9.0
```

Aucun nouveau secret n’est requis.

## 3. Déployer la nouvelle interface

Dans GitHub :

```text
Actions
→ Deploy production
→ Run workflow
```

Gardez le déploiement web, le cron et la vérification navigateur activés.

Résultat attendu :

```text
API ok · v3.9.0
```

Avant recalcul, la page Preuves peut afficher **Recalcul requis**. C’est volontaire : les anciens ratios V3.8 sont masqués.

## 4. Recalculer le vrai lot sans crédit

Dans GitHub :

```text
Actions
→ Recompute latest evidence
→ Run workflow
```

Ce workflow :

- télécharge le dernier artefact `historical-sample-evidence-*` ;
- n’appelle pas The Odds API ;
- ne demande ni `THE_ODDS_API_KEY` ni `DATABASE_URL` ;
- recalcule le funnel et la matrice bookmaker ;
- exécute les tests ;
- publie les nouveaux artefacts ;
- redéploie le dashboard ;
- vérifie la production.

## 5. Lire le résultat

La page doit distinguer :

```text
Intégrité technique
Couverture fournisseur
Matching résultats
Consensus
Winamax
Preuve statistique
```

La couverture fournisseur est désormais :

```text
cibles retournées / cibles exécutées
```

et non plus :

```text
événements avec cotes / tous les événements découverts
```

## Cas d’échec explicites

### Aucun artefact non expiré

Le workflow s’arrête avec :

```text
No non-expired historical-sample-evidence artifact was found
```

Aucun crédit n’est consommé. Il faudra fournir une copie téléchargée de l’ancien artefact ou décider explicitement d’un nouveau petit lot.

### Configuration Railway manquante

Le workflow liste en une seule fois :

```text
RAILWAY_TOKEN
RAILWAY_PROJECT_ID
APP_PUBLIC_URL
```

### Rapport qualité bloqué

Un blocage de qualité n’est pas un échec de déploiement. Le rapport est publié avec les raisons exactes.
