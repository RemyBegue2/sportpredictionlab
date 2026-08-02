# Architecture cloud V3.3

```text
Navigateur authentifié
        |
        v
Service web FastAPI
        |
        +---- PostgreSQL <---- shadow-cron toutes les 15 min
        |                           |
        |                           +---- The Odds API
        |
        +---- artefacts modèles vérifiés

Worker historique manuel ---- The Odds API historical
```

## Service web

Interface, prédictions interactives, lecture des journaux, santé et readiness.

## Shadow cron

Processus fini : cotes actuelles, prédictions immuables, résultats dus, règlement, journal du cycle.

## Worker historique

Backfills coûteux avec plan et plafond. Il ne tourne pas automatiquement.

## Base

Événements, snapshots, prédictions interactives, résultats, shadow, modèles et benchmarks.
