# Sports Prediction Lab V3.2 — Real Historical Benchmark

> **V3.2.1** corrige un faux statut « API indisponible » provoqué par l'affichage d'un intervalle de confiance encore absent avant le premier benchmark.


Application privée de recherche pour le football et le tennis. La V3.2 conserve le déploiement cloud de la V3.1 et ajoute une chaîne reproductible pour confronter les probabilités du modèle à Winamax, au consensus dévigé et à la closing line.

## Verdict actuel

- **GO technique** pour une instance privée Railway/Render.
- **GO collecte contrôlée** avec dry-run, plafond de crédits et reprise sur incident.
- **NO-GO statistique** tant qu’un benchmark historique réel suffisamment large n’a pas été exécuté.
- **NO-GO automatisation de paris** : aucune connexion au compte, aucune mise, aucun placement automatique.

L’archive ne contient ni clé The Odds API ni résultat historique inventé.

## Nouveautés V3.2

- planification historique à plusieurs horizons ;
- worker Railway séparé du service web ;
- téléchargement reprenable, par fragments immuables ;
- budget estimé et plafond dur avant chaque appel ;
- séparation correcte des snapshots d’un même événement ;
- collecte des résultats récents via l’endpoint scores ;
- rapprochement événement/résultat avec score de confiance et veto d’ambiguïté ;
- audit temporel strict ;
- folds chronologiques en fenêtre croissante ;
- comparaison modèle, Winamax, consensus et blend appris sur le passé seulement ;
- log-loss, Brier, RPS, calibration, bootstrap par blocs et CLV ;
- stockage PostgreSQL des résultats, jobs, problèmes de qualité et benchmarks ;
- écran « Validation marché » et endpoints d’administration.

## Installation locale

```bash
python -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
python -m scripts.train_snapshot
uvicorn webapp:app --reload
```

Ouvrir `http://localhost:8000`.

## Déploiement Railway

La V3.2 reprend la configuration qui a fonctionné pour la V3.1.2.

Variables minimales du service web :

```text
APP_ENV=production
APP_AUTH_REQUIRED=true
APP_COOKIE_SECURE=true
APP_PASSWORD=<12 caractères minimum>
APP_SESSION_SECRET=<32 caractères minimum>
DATABASE_URL=${{Postgres.DATABASE_URL}}
THE_ODDS_API_KEY=<secret Railway>
ODDS_SYNC_SPORTS=soccer_epl
ODDS_STALE_MINUTES=15
MODEL_VERSION=3.2.0
```

Le service principal utilise `railway.toml`. Le cron courant utilise `railway.cron.toml`. Le backfill historique utilise `railway.worker.toml` et doit être déclenché manuellement après vérification de son budget.

## Workflow historique recommandé

### 1. Découvrir les événements

```bash
python -m scripts.discover_historical_events \
  --sport-key soccer_epl \
  --start 2024-08-01 \
  --end 2025-05-31
```

Relancer avec `--execute` seulement après inspection du plan.

### 2. Construire un plan budgété

```bash
python -m scripts.plan_historical_backfill \
  --events-csv data/odds_api/historical/events.csv \
  --horizons 24 6 1 \
  --closing-minutes 10 \
  --max-credits 5000
```

Cette commande ne consomme aucun crédit.

### 3. Exécuter le backfill

```bash
python -m scripts.run_historical_backfill \
  --plan-dir data/odds_api/backfill \
  --max-credits 5000 \
  --execute
```

Chaque requête terminée est enregistrée dans `state.json`. Une relance reprend les requêtes manquantes et réutilise le cache fournisseur.

### 4. Préparer les lignes d’évaluation

Le CSV de résultats doit utiliser le schéma normalisé :

```text
date,league,home_team,away_team,home_goals,away_goals
```

Puis :

```bash
python -m scripts.prepare_market_benchmark \
  --results-csv data/real/football_real.csv \
  --events-csv data/odds_api/historical/events.csv \
  --odds-csv data/odds_api/backfill/historical_odds_long.csv \
  --stage t-1h \
  --initial-train 600
```

Les correspondances ambiguës restent dans `data/benchmark/event_mapping.csv` mais sont exclues du benchmark.

### 5. Lancer le benchmark

```bash
python -m scripts.run_market_benchmark \
  --input data/benchmark/evaluation_t-1h.csv \
  --sport-key soccer_epl \
  --minimum-predictions 500 \
  --persist
```

Le rapport est écrit dans `artifacts/market_benchmark_v3_2.json` et, avec `--persist`, dans PostgreSQL.

## Endpoints V3.2

```text
GET  /api/benchmark/summary
GET  /api/admin/data-quality
GET  /api/admin/backfills
GET  /api/history/predictions
GET  /api/history/sync-runs
POST /api/odds/historical/estimate
```

Tous les endpoints, sauf liveness et authentification, sont protégés lorsque `APP_AUTH_REQUIRED=true`.

## Tests

```bash
pytest -q
coverage run -m pytest
coverage report -m
```

État livré : **59 tests réussis**, **85,44 % de couverture globale**.

## Documents

- `AUDIT_MULTI_ROLES_V3_2.md`
- `HISTORICAL_BENCHMARK_GUIDE.md`
- `RESULTATS_V3_2.md`
- `MODEL_CARD.md`
- `SECURITY.md`
- `DEPLOY_RAILWAY.md`
- `ROADMAP_V3.md`
