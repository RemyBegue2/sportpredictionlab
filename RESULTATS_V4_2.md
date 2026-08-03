# Résultats de validation — V4.2.0

## Tests

La suite a été exécutée par quatre lots indépendants :

- lot 1 : 37 réussis ;
- lot 2 : 31 réussis ;
- lot 3 : 43 réussis ;
- lot 4 : 70 réussis ;
- total : **181 réussis, 0 échec**.

L'exécution monolithique avec couverture a dépassé la limite de l'environnement après le premier lot. La couverture a donc été agrégée avec `coverage --append` sur les quatre lots.

## Couverture

- total cœur : **83 %** ;
- `coverage_preflight.py` : **87 %** ;
- `evidence_campaign.py` : **83 %** ;
- `evidence_quality.py` : **90 %** ;
- `webapp.py` : **78 %**.

## Validations statiques

- compilation Python : réussie ;
- syntaxe JavaScript : réussie ;
- YAML : 12 workflows GitHub et `render.yaml` valides ;
- version application : `4.2.0` ;
- version paquet : `0.4.2.0` ;
- aucun `railway up --ci` dans les workflows.

## Non validé dans l'environnement réel

- aucun appel réel The Odds API ;
- aucun crédit réel consommé ;
- aucun préflight V4.2 publié ;
- aucun déploiement Railway V4.2 ;
- aucune campagne payante V4.2.
