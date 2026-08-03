# Hotfix V3.9.2 — Railway CI runtime detection

## Cause

Le workflow GitHub définit `RAILWAY_ENVIRONMENT=production` pour cibler Railway. Cette variable ne signifie pas que le processus pytest tourne dans un service Railway.

La V3.9 avait réintroduit l'ancien test :

```python
bool(os.getenv("RAILWAY_ENVIRONMENT") or os.getenv("RENDER"))
```

Les tests SQLite étaient donc refusés comme s'ils s'exécutaient en production Railway.

## Correctif

Le runtime cloud n'est détecté que grâce aux marqueurs réellement injectés dans un service :

- `RAILWAY_SERVICE_ID`
- `RAILWAY_ENVIRONMENT_ID`
- `RENDER_SERVICE_ID`
- `RENDER`

`RAILWAY_ENVIRONMENT` seul reste une simple cible distante de CI.

## Fichiers

- `sports_predictor/cloud_config.py`
- `scripts/db_migrate.py`
- `tests/test_deployment_entrypoints.py`

## Validation

Exécution avec l'environnement exact qui causait la panne :

```text
RAILWAY_ENVIRONMENT=production
RAILWAY_SERVICE_ID absent
```

Résultat :

```text
136 passed
```

Le test production réel conserve son comportement en ajoutant explicitement `RAILWAY_SERVICE_ID`.
