# Sports Prediction Lab V3.3 — Shadow Mode

Application web privée de recherche sur les probabilités football/tennis, les cotes Winamax via The Odds API et la validation en conditions réelles.

## Nouveauté principale

La V3.3 enregistre automatiquement des prédictions pré-match à quatre jalons, récupère les résultats et mesure la qualité du modèle. Elle ne place aucun pari.

Le modèle football embarqué est volontairement marqué **degraded** : ses 90 matchs s’arrêtent au 23 octobre 2023. Toute sélection opérationnelle est donc bloquée jusqu’au réentraînement. Le tennis reste expérimental et non calibré.

## Déploiement Railway

Le service web utilise `railway.toml`. Après mise à jour du dépôt, crée un second service avec `/railway.cron.toml` afin d’exécuter le shadow mode toutes les quinze minutes.

Guide complet : [DEPLOY_RAILWAY.md](DEPLOY_RAILWAY.md).

## Variables principales

```text
APP_ENV=production
APP_AUTH_REQUIRED=true
APP_COOKIE_SECURE=true
APP_PASSWORD=...
APP_SESSION_SECRET=...
DATABASE_URL=${{Postgres.DATABASE_URL}}
THE_ODDS_API_KEY=...
MODEL_VERSION=3.3.0
ODDS_SYNC_SPORTS=soccer_epl
SHADOW_MODE_ENABLED=true
SHADOW_QUOTA_FLOOR=100
MODEL_MAX_AGE_DAYS=365
```

## Exécution locale

```bash
pip install -r requirements.txt
python -m scripts.train_snapshot
uvicorn webapp:app --reload
```

## Tests

État livré : **71 tests réussis**, **85 % de couverture globale**.

```bash
pytest -q
coverage run -m pytest -q
coverage report
```

## Endpoints importants

```text
/api/health
/api/ready
/api/shadow/summary
/api/shadow/predictions
/api/models
/api/odds/football/slate
/api/benchmark/summary
```

## Services

- `railway.toml` : web ;
- `railway.cron.toml` : shadow mode ;
- `railway.worker.toml` : historique manuel.

## Documentation

- `AUDIT_MULTI_ROLES_V3_3.md` ;
- `SHADOW_MODE_GUIDE.md` ;
- `RESULTATS_V3_3.md` ;
- `MODEL_CARD.md` ;
- `SECURITY.md` ;
- `RESPONSIBLE_USE.md`.

## Limites

Aucune performance actuelle n’est démontrée. Aucun résultat shadow réel n’est inclus dans l’archive. Les historiques de cotes peuvent consommer un quota important. L’application est prévue pour un usage privé mono-utilisateur.
