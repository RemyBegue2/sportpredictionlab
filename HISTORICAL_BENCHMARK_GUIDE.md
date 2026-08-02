# Guide du benchmark historique V3.2

## Objectif

Comparer, sur des événements futurs par rapport à chaque entraînement :

1. le modèle sportif ;
2. Winamax dévigué ;
3. un consensus hors Winamax ;
4. un blend dont le poids est appris uniquement sur le passé.

## Données requises

- événements historiques The Odds API ;
- snapshots `h2h` à 24 h, 6 h, 1 h et environ 10 minutes avant le départ ;
- résultats normalisés ;
- au moins plusieurs centaines de rencontres après la fenêtre initiale.

The Odds API ne fournitissant les scores terminés que sur une fenêtre récente, les résultats de saisons anciennes doivent venir d’une source historique séparée et être rapprochés avec les événements.

## Étapes

### A. Découverte

```bash
python -m scripts.discover_historical_events --sport-key soccer_epl --start 2024-08-01 --end 2025-05-31
```

### B. Dry-run budgétaire

```bash
python -m scripts.plan_historical_backfill \
  --events-csv data/odds_api/historical/events.csv \
  --horizons 24 6 1 \
  --closing-minutes 10 \
  --max-credits 5000
```

Contrôler `data/odds_api/backfill/plan.json`.

### C. Exécution

```bash
python -m scripts.run_historical_backfill \
  --plan-dir data/odds_api/backfill \
  --max-credits 5000 \
  --execute
```

Ne pas supprimer `state.json` ni le dossier `chunks` pendant une reprise.

### D. Préparation

```bash
python -m scripts.prepare_market_benchmark \
  --results-csv data/real/football_real.csv \
  --events-csv data/odds_api/historical/events.csv \
  --odds-csv data/odds_api/backfill/historical_odds_long.csv \
  --stage t-1h \
  --initial-train 600
```

Inspecter :

- `event_mapping.csv` ;
- `preparation_report.json` ;
- `evaluation_t-1h.csv`.

Un taux de matching inférieur à 98 % doit être expliqué avant promotion.

### E. Benchmark

```bash
python -m scripts.run_market_benchmark \
  --input data/benchmark/evaluation_t-1h.csv \
  --minimum-predictions 500 \
  --folds 5 \
  --persist
```

## Lecture du verdict

- `not_run` : aucune exécution réelle ;
- `not_evaluable` : pas de fold ou échantillon insuffisant ;
- `exploratory` : signal préliminaire seulement ;
- `preliminary_go` : intervalle favorable, sans garantie financière ;
- `no_go` : avantage robuste non démontré.

## Contrôles obligatoires

- aucune cote après la création de la prédiction ;
- aucune prédiction au départ ou après le départ ;
- événements ambigus exclus ;
- marché Winamax complet ;
- consensus contenant au moins un autre bookmaker ;
- poids du blend appris sur le train ;
- même date jamais coupée entre train et test ;
- closing line utilisée uniquement pour l’évaluation.
