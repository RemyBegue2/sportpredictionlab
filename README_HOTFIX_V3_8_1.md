# Hotfix V3.8.1 — Historical range sampling

## Bug corrigé

Le workflow `Estimate historical sample` convertissait chaque jour de la période demandée en un appel de découverte. Une période de 1 308 jours nécessitait donc 1 308 appels et échouait immédiatement devant le plafond de 14.

## Nouveau comportement

- période courte : un appel par jour, dans la limite configurée ;
- période longue : dates de découverte réparties uniformément entre le début et la fin ;
- le premier et le dernier jour sont toujours inclus ;
- le nombre d'appels ne dépasse jamais `max_discovery_calls` ;
- les événements retenus pour le lot sont eux aussi répartis sur toute la période au lieu de prendre uniquement les premiers matchs.

Exemple : une période de 1 308 jours avec un plafond de 14 produit exactement 14 dates de découverte, pas 1 308.

## Fichiers remplacés

- `.github/workflows/estimate-historical-sample.yml`
- `.github/workflows/run-historical-sample.yml`
- `sports_predictor/sample_plan.py`
- `scripts/discover_historical_events.py`
- `scripts/plan_historical_backfill.py`
- `tests/test_v38_evidence_run.py`

Aucune variable Railway, aucun secret et aucun modèle ne doivent être modifiés.
