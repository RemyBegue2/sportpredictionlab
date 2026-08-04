# Sports Prediction Lab — point de reprise V4.9.0

## État préparé

- Version : **4.9.0 — Controlled Model Decision & Live Validation**.
- Interface : Aujourd’hui, Signaux, Apprentissage ; un seul écran actif.
- Football : deux challengers réellement entraînés, tous deux en `hold`.
- Holdout : ancienne génération consultée uniquement pour diagnostic ; nouvelle génération future ouverte.
- Tennis : import incrémental et catalogue prêts, données livrées encore insuffisantes.
- Production : deux sessions longues séparées simple/expert à exécuter sur l’URL publique.
- Coût fournisseur de l’entraînement et des imports : zéro.

## Première action

1. Déployer V4.9.0 avec `verify_browser=true`.
2. Vérifier `/api/ready`, `/api/release` et `/api/controlled-model-decision`.
3. Lancer `Run controlled model decision` avec `RUN_CONTROLLED_MODEL_DECISION`.
4. Exécuter `Verify public long session` pendant 1 800 secondes pour les scénarios simple et expert.
5. Importer les prochains lots tennis avec `scripts.import_tennis_incremental`.
6. Conserver les captures payantes fermées pendant ces vérifications.

## Règles

- le holdout déjà consulté ne sert jamais à promouvoir un challenger V4.9 ;
- un nouveau holdout exige 30 dates futures après le cutoff actuel ;
- un challenger `hold` ne remplace jamais le champion ;
- un dataset tennis corrigé produit une nouvelle version ;
- aucune bankroll réelle, mise personnalisée ou action bookmaker ;
- aucune promotion automatique.
