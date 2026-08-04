# Runbook opérationnel — V4.9.0

## Déploiement fermé

```text
DAILY_ODDS_ENABLED=false
DAILY_ODDS_MAX_CREDITS=0
SHADOW_MODE_ENABLED=false
AUTOMATED_SHADOW_ENABLED=false
HISTORICAL_EVIDENCE_ENABLED=false
```

Le pre-deploy doit exécuter :

```bash
python -m scripts.db_migrate
```

Vérifier :

```text
/api/ready                       ready
/api/release                     version 4.9.0
/api/controlled-model-decision   hold, collecting ou review_required
```

## Tour de décision contrôlé

Workflow :

```text
Run controlled model decision
confirmation: RUN_CONTROLLED_MODEL_DECISION
```

Attendus avec les données livrées :

```text
football.status = hold
football.challengers = 2
football.promotion_ready = false
tennis.training_status = blocked_below_readiness_gates
production_validation.status = not_proven
limits.provider_credits_consumed = 0
limits.automatic_promotion = false
```

Ne pas utiliser le holdout historique consulté pour retuner les deux challengers.

## Import tennis incrémental

```bash
python -m scripts.import_tennis_incremental \
  --previous artifacts/tennis_previous/accepted.csv \
  --incoming data/imports/tennis_new.csv \
  --previous-dataset-id DS-TENNIS-... \
  --source <source_documentée> \
  --license-status research_only \
  --output-dir artifacts/tennis_incremental_v4_9
```

Contrôler :

- `accepted.csv` ;
- `quarantined.csv` ;
- `catalog.json` ;
- `new_rows` ;
- `unchanged_duplicates` ;
- `result_corrections` ;
- nouveau `dataset_id` ;
- `supersedes_dataset_id`.

## Validation publique longue session

Workflow :

```text
Verify public long session
base_url: URL publique
duration_seconds: 1800
```

Le workflow lance deux jobs :

```text
simple
expert
```

Attendus :

- `status = ok` ;
- aucune erreur console/page ;
- croissance DOM et réseau sous les seuils ;
- un seul panneau simple actif ;
- version 4.9.0 ;
- rapports `public_long_session_v4_9_simple.json` et `public_long_session_v4_9_expert.json`.

## Incident challenger

- conserver le champion actuel ;
- ne pas ouvrir The Odds API ;
- vérifier le dataset et les partitions ;
- vérifier les vetos nul, victoire extérieure et repos déséquilibré ;
- ne pas modifier les hyperparamètres après consultation d’un holdout ;
- créer une nouvelle expérience pour toute modification.

## Incident tennis

- conserver le statut bloqué ;
- examiner la quarantaine ;
- corriger la source ou le mapping ;
- produire une nouvelle version ;
- ne jamais écraser l’ancien dataset ;
- ne pas abaisser les seuils.
