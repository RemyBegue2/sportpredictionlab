# Déploiement Render Blueprint — V3.1

Le fichier `render.yaml` provisionne le web, PostgreSQL et le cron.

## Étapes

1. Publiez le projet dans GitHub.
2. Dans Render, créez un Blueprint depuis le dépôt.
3. Render détecte `render.yaml`.
4. Saisissez les secrets demandés :
   - `APP_PASSWORD` ;
   - `THE_ODDS_API_KEY` pour le web ;
   - `THE_ODDS_API_KEY` pour le cron.
5. Vérifiez le récapitulatif de facturation avant création.
6. Attendez le pre-deploy `python scripts/db_migrate.py`.
7. Ouvrez l'URL du service web et connectez-vous.

## Ressources déclarées

- web Docker `starter`, région Frankfurt ;
- cron Docker `starter`, toutes les quinze minutes ;
- PostgreSQL `basic-256mb`, région Frankfurt ;
- connexion DB privée par `fromDatabase` ;
- aucun accès public direct à PostgreSQL (`ipAllowList: []`).

## Limite Render

Le cron n'utilise pas de disque persistant. Ce projet stocke donc toute donnée durable dans PostgreSQL, ce qui est compatible avec cette contrainte.
