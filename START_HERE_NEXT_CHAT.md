# Sports Prediction Lab — point de reprise V4.1

## État préparé

- Version du code : **4.1.1 — Decision Integrity & Resumable Operations**.
- Exploitation : GitHub Actions + Railway, sans Python local.
- Workflow principal : **Run evidence campaign**.
- Modes : `dry_run`, `recompute_only`, `continue_current_stage`, `start_next_stage`.
- Stages contrôlés : 30, 100, 300 et 1 000 événements prêts pour benchmark.
- Baselines : `consensus` ou `winamax`.

## Garanties ajoutées en V4.1

- verdict unique `PASS/HOLD/FAIL` ;
- aucun contournement du stage suivant par le mode de reprise ;
- matching bijectif et collisions bloquantes ;
- consensus avec au moins deux bookmakers indépendants ;
- décision spécifique à la baseline choisie ;
- reprise depuis un checkpoint de découverte partiel ;
- total des crédits = découverte + snapshots ;
- readiness réelle via `/api/ready` ;
- verrou commun pour les modifications de production.

## État de validation

- 161 tests réussis par lots, dont 6 régressions V4.1.1 ;
- couverture cœur : 83 % ;
- Python, JavaScript et YAML validés ;
- aucun appel réel à The Odds API effectué pendant la préparation ;
- aucun déploiement GitHub Actions/Railway effectué pendant la préparation.

## Prochaine action sûre

1. Fusionner la V4.1 dans GitHub.
2. Lancer **Deploy production**.
3. Vérifier `/api/ready` et `/api/release`.
4. Lancer **Run evidence campaign → dry_run → stage 30**.
5. N’autoriser une campagne payante ou le stage 100 qu’après lecture d’un rapport V4.1 réel.

Ne jamais promouvoir automatiquement un modèle, recommander une mise ou placer un pari.
