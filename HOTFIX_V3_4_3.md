# V3.4.3 — correctif interface et déploiement Railway

## Corrections

- Suppression de l'accès JavaScript à l'élément inexistant `#benchmarkState`.
- Test de contrat vérifiant que chaque sélecteur d'identifiant utilisé par `static/app.js` existe dans `static/index.html`.
- Cache-busting du JavaScript en `v=3.4.3`.
- Le workflow de reconstruction déploie explicitement le service web et `shadow-cron` avec Railway CLI après avoir poussé les nouveaux artefacts.

## Secrets GitHub requis

- `RAILWAY_TOKEN` : Project Token Railway limité au projet/environnement.
- `RAILWAY_PROJECT_ID` : identifiant du projet Railway.

Variables GitHub facultatives :

- `RAILWAY_ENVIRONMENT` (défaut `production`)
- `RAILWAY_WEB_SERVICE` (défaut `sportpredictionlab`)
- `RAILWAY_CRON_SERVICE` (défaut `shadow-cron`)
