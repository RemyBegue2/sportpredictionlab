# Résultats de validation — V4.9.0

## Tests

- **266 tests collectés** ;
- **266 tests réussis** ;
- **0 échec** ;
- exécution en six lots disjoints : `39 + 46 + 50 + 46 + 60 + 25`.

La suite monolithique a dépassé la limite de durée après avoir lancé les premiers tests. Chaque fichier appartient à un seul lot et l’ensemble des 266 tests collectés est couvert.

## Couverture ciblée

Lot instrumenté : tests V4.9.

- `sports_predictor/controlled_decision.py` : **89 %** combiné branches/instructions ;
- 5 tests V4.9 instrumentés réussis.

## Tour football réel

Dataset :

- 1 900 matchs ;
- 583 dates ;
- 1 028 lignes d’entraînement ;
- 250 lignes de calibration ;
- 229 lignes de validation développement ;
- 393 lignes dans le holdout déjà consulté, exclu de la sélection V4.9.

Baseline Elo sur la validation développement :

- log loss : **0,9945** ;
- Brier : **0,5972** ;
- ECE : **0,0465**.

Poisson régularisé :

- log loss : **0,9850** ;
- Brier : **0,5904** ;
- ECE : **0,0525** ;
- veto : nul et repos déséquilibré ;
- verdict : `hold`.

Hybride Poisson/Elo :

- log loss : **0,9868** ;
- Brier : **0,5923** ;
- ECE : **0,0750** ;
- veto : ECE, nul et repos déséquilibré ;
- verdict : `hold`.

Nouvelle génération de promotion :

- statut : `open_collecting` ;
- début après : 24 mai 2026 ;
- 30 nouvelles dates distinctes requises ;
- promotion prête : `false`.

## Tennis

- 32 matchs ;
- 2 dates ;
- exploration : 500 matchs et 50 dates requis ;
- challenger : 1 500 matchs et 150 dates requis ;
- import incrémental testé avec ajouts, doublon inchangé et correction de résultat ;
- ancien dataset conservé via `supersedes_dataset_id` ;
- verdict : `blocked_below_readiness_gates`.

## Production

- scénario longue session simple : `not_run` ;
- scénario longue session expert : `not_run` ;
- statut consolidé : `not_proven`.

Le workflow est fourni, mais aucune preuve publique n’est inventée.

## Validations techniques

- compilation de 89 fichiers Python ;
- syntaxe `static/app.js` validée avec Node ;
- 23 workflows GitHub chargés avec PyYAML ;
- 53 références `actions/*` vérifiées comme SHA complets ;
- version Python/package : `4.9.0 / 0.4.9.0` ;
- frontend : `app.js?v=4.9.0` ;
- aucun appel réel à The Odds API ;
- aucun crédit réel consommé ;
- aucun déploiement Railway réalisé.

## Fonctionnalités validées

- exactement deux challengers football ;
- sélection antérieure au holdout consulté ;
- nouveau holdout futur non consulté ;
- vetos par sous-groupe ;
- import tennis incrémental versionné ;
- correction de résultat sans écrasement historique ;
- validation publique simple/expert séparée ;
- endpoint et workflow zéro crédit ;
- interface toujours limitée à trois onglets ;
- promotion automatique interdite.
