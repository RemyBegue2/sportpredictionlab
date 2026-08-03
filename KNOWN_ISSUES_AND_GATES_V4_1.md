# Risques résiduels et portes — V4.1

## Portes bloquantes avant le stage 100

Le stage 100 reste interdit tant qu’un rapport réel V4.1 du stage 30 n’affiche pas `PASS` avec :

- zéro violation temporelle ;
- zéro doublon ;
- zéro collision de matching ;
- couverture fournisseur d’au moins 80 % ;
- matching fiable d’au moins 95 % ;
- couverture de la baseline choisie d’au moins 70 % ;
- au moins 30 événements uniques prêts pour benchmark ;
- crédits totaux sous le plafond ;
- cohérence entre GitHub Actions, l’artefact, Railway et l’API.

## Risques P1 non bloquants pour le déploiement V4.1

1. Les migrations de schéma utilisent encore principalement `create_all()` ; Alembic reste à introduire avant des changements complexes de base.
2. Les actions GitHub sont référencées par tags majeurs (`@v4`, `@v5`) plutôt que par SHA immuables.
3. Les artefacts bruts de campagne sont conservés 90 jours, pas indéfiniment.
4. Le rate limiter de connexion reste local au processus et la confiance dans les en-têtes proxy doit être documentée pour une topologie multi-instance.
5. La suite monolithique `pytest -q` a dépassé la limite de l’environnement d’audit ; les 155 tests ont tous réussi par quatre lots indépendants.
6. La V4.1 n’a pas été déployée depuis l’environnement de préparation et n’a effectué aucun appel réel à The Odds API.

## Hors périmètre

- nouveaux championnats ;
- nouveaux marchés ;
- extension tennis ;
- optimisation ou recommandation de mise ;
- placement automatique ;
- promotion automatique ;
- conclusion de rentabilité.
