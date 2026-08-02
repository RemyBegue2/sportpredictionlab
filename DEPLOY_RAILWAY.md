# Déployer V3.5 sur Railway

## Mise à niveau sûre

Utiliser le paquet `sports_prediction_v3_5_upgrade.zip`. Il ne contient pas les modèles ni `data/real/`, afin de préserver les artefacts frais créés par GitHub Actions.

Après le push, mettre sur le web et le cron :

```text
MODEL_VERSION=3.5.0
```

Puis déployer le dernier commit.

## Vérification

```text
GET /api/health
GET /api/release
```

Contrôler :

```text
version = 3.5.0
source_commit = commit déployé
artifact_integrity_ok = true
football_model_sha256 = hash attendu
```

## Post-déploiement GitHub Actions

Secrets :

```text
RAILWAY_TOKEN
RAILWAY_PROJECT_ID
```

Variables :

```text
RAILWAY_ENVIRONMENT=production
RAILWAY_WEB_SERVICE=sportpredictionlab
RAILWAY_CRON_SERVICE=shadow-cron
APP_PUBLIC_URL=https://votre-domaine.up.railway.app
```

`APP_PUBLIC_URL` active la preuve post-déploiement. Sans elle, le workflow peut déployer mais ne peut pas confirmer que l’URL publique sert la bonne release.

## Base de données

Le pre-deploy `python -m scripts.db_migrate` crée les tables :

- `release_registry` ;
- `model_status_transitions`.

Aucune table existante n’est supprimée.
