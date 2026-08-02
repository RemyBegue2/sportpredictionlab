# Sports Prediction Lab V3.6

Application privée de recherche football/tennis avec FastAPI, PostgreSQL, The Odds API, shadow mode pré-match, preuve de déploiement et moteur **champion–challenger**.

## Ce que V3.6 ajoute

- endpoint privé `/api/model-decision` avec verdict déterministe et portes de promotion explicites ;
- collecte shadow simultanée du champion, de Winamax, du consensus dévigé et d’un blend 50/50 ;
- benchmark multi-contenders sur les mêmes lignes, les mêmes folds chronologiques et les mêmes contrôles temporels ;
- challenger historique `blend50` généré dans le dataset de benchmark ;
- plan de backfill immuable avec SHA-256, plafond de crédits et validation limitée par défaut à 30 événements ;
- approbation exacte du `plan_id` obligatoire pour un backfill complet ;
- checkpoints reprenables, hash des chunks et journalisation des erreurs de collecte ;
- registre PostgreSQL des décisions de modèle ;
- page « Décision modèle » dans l’interface ;
- handoff enrichi avec modèle actif, dernier benchmark et prochaines actions.

## Ce que V3.6 ne prétend pas

- aucun benchmark historique réel n’a été exécuté dans le paquet livré ;
- aucun crédit The Odds API historique n’a été consommé ;
- aucune supériorité face à Winamax ou au consensus n’est démontrée ;
- aucune promotion de modèle n’est automatique ;
- aucun pari, aucune taille de mise et aucune connexion à un compte Winamax.

## Mise à niveau depuis V3.5

Le paquet d’upgrade omet volontairement les modèles et données actives. Ne remplacez pas :

```text
artifacts/football_model.joblib
artifacts/tennis_model.joblib
artifacts/metrics.json
artifacts/artifact_manifest.json
artifacts/fresh_rebuild_report.json
data/real/
```

Décompressez l’upgrade à la racine du dépôt :

```bash
git add -A
git commit -m "Upgrade to V3.6 evidence engine"
git push
```

Sur Railway, définissez sur `sportpredictionlab` et `shadow-cron` :

```text
MODEL_VERSION=3.6.0
```

Puis déployez le dernier commit sur les deux services.

## Vérification

```text
GET /api/health
GET /api/release
GET /api/model-decision
```

Le résultat attendu au premier démarrage est généralement `not_evaluable`, car aucun benchmark réel suffisant n’existe encore. C’est le comportement correct.

## Premier benchmark réel recommandé

1. Préparer un échantillon de 30 événements :

```bash
python -m scripts.plan_historical_backfill \
  --events-csv data/benchmark/events.csv \
  --max-credits 200 \
  --sample-events 30
```

2. Vérifier `data/odds_api/backfill/plan.json`.
3. Faire un dry-run :

```bash
python -m scripts.run_historical_backfill \
  --plan-dir data/odds_api/backfill \
  --max-credits 200
```

4. Exécuter seulement après validation :

```bash
python -m scripts.run_historical_backfill \
  --plan-dir data/odds_api/backfill \
  --max-credits 200 \
  --execute
```

5. Préparer puis comparer les contenders :

```bash
python -m scripts.prepare_market_benchmark \
  --results-csv data/real/football_active.csv \
  --events-csv data/benchmark/events.csv \
  --odds-csv data/odds_api/backfill/historical_odds_long.csv \
  --stage t-1h

python -m scripts.run_champion_challenger \
  --input data/benchmark/evaluation_t-1h.csv \
  --contenders model blend50 \
  --champion model \
  --persist
```

Un plan complet de plus de 30 événements exige en plus :

```text
--approve-plan <PLAN_ID exact>
```

## Handoff pour une nouvelle conversation

```bash
python -m scripts.generate_release_manifest
python -m scripts.export_handoff
```

Joindre ensuite :

```text
START_HERE_NEXT_CHAT.md
handoff/HANDOFF_CURRENT.md
handoff/HANDOFF_CURRENT.json
handoff/LAST_BENCHMARK_SUMMARY.json
handoff/ACTIVE_MODEL_CARD.md
handoff/NEXT_ACTIONS.md
artifacts/release_manifest.json
```

## Validation locale de cette livraison

- 99 tests réussis ;
- couverture globale : 85 % ;
- compilation de 82 fichiers Python réussie ;
- syntaxe JavaScript valide ;
- YAML et TOML valides ;
- scan de secrets : aucun secret réel détecté.
