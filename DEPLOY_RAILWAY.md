# Déployer la V3.4 sur Railway

## Mise à jour du service web

1. Copier le contenu de l'archive à la racine du dépôt.
2. Commit et push.
3. Vérifier `/api/health` : la version doit être `3.4.0`.
4. Mettre `MODEL_VERSION=3.4.0` dans les variables du service.

Le pre-deploy lance `python -m scripts.db_migrate` et crée les nouvelles tables.

## Mise à jour de shadow-cron

Le service existant conserve `/railway.cron.toml`. Mettre également `MODEL_VERSION=3.4.0` puis déployer le dernier commit.

Le prochain cycle doit afficher des compteurs dans **Shadow → Pourquoi zéro ?**.

## Reconstruction du modèle

Ne pas entraîner le modèle dans le cron Railway. Déclencher le workflow GitHub Actions fourni. Celui-ci commit les artefacts générés ; Railway redéploie ensuite l'image contenant le modèle promu.

## Vérifications

- `/api/health` répond `3.4.0` ;
- `/api/ready` répond `ready` ;
- le dernier cycle indique durée et quota ;
- les diagnostics expliquent les exclusions ;
- le modèle reste `degraded` tant qu'aucun candidat n'est promu.
