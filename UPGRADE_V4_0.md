# Mise à niveau V3.9.2 → V4.0 sans Python local

## 1. Copier l’upgrade

Décompresse l’archive V4.0 à la racine du dépôt GitHub et accepte les remplacements.

Le chemin suivant doit exister :

```text
.github/workflows/run-evidence-campaign.yml
```

L’archive d’upgrade ne contient pas `data/` ni les modèles actifs.

## 2. Créer le commit

Depuis l’interface GitHub, crée le commit :

```text
Upgrade to V4.0 controlled evidence scale-up
```

## 3. Mettre à jour Railway

Dans les variables des services `sportpredictionlab` et `shadow-cron` :

```text
MODEL_VERSION=4.0.0
```

Ne modifie pas `DATABASE_URL`, les modèles ou les clés.

## 4. Déployer

```text
GitHub → Actions → Deploy production → Run workflow
```

Le déploiement attendu affiche `API ok · v4.0.0`.

## 5. Lancer le plan gratuit

```text
GitHub → Actions → Run evidence campaign → Run workflow
```

Valeurs initiales :

```text
mode = dry_run
target_stage = 30
max_credits = 350
baseline = consensus
confirmation = vide
```

Ce mode exécute les tests et le plan, puis publie un artefact. Il n’appelle pas The Odds API.

## 6. Exécuter le stage 30

Seulement après lecture du dry-run :

```text
mode = start_next_stage
target_stage = 30
max_credits = valeur approuvée
baseline = consensus
confirmation = EXECUTE_CAMPAIGN
```

Secrets nécessaires pour les modes payants :

```text
THE_ODDS_API_KEY
RAILWAY_TOKEN
RAILWAY_PROJECT_ID
```

Variable GitHub nécessaire :

```text
APP_PUBLIC_URL
```

`DATABASE_URL` n’est pas utilisé par ce workflow.

## 7. Reprendre un stage interrompu

Relance le workflow avec :

```text
mode = continue_current_stage
même target_stage
même max_credits
même baseline
confirmation = EXECUTE_CAMPAIGN
```

Le workflow cherche le dernier artefact `evidence-campaign-state-*`. Il restaure le checkpoint uniquement lorsque les paramètres et les dates correspondent. Sinon, il annonce un démarrage frais.
