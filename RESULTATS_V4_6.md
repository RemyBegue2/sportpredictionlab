# Résultats de validation — V4.6.0

## Tests

- 245 tests collectés ;
- 245 tests réussis ;
- 0 échec ;
- exécution en sept lots disjoints : 32 + 24 + 29 + 47 + 29 + 40 + 44.

La suite monolithique n’a pas été utilisée comme preuve, afin d’éviter la limite de durée déjà observée dans l’environnement d’audit.

## Couverture ciblée

Lot instrumenté : tests V4.5, V4.6 et webapp.

- `sports_predictor/feature_lab.py` : **79 %** combiné branches/instructions ;
- 30 tests instrumentés réussis ;
- la couverture ciblée ne remplace pas les sept lots fonctionnels complets.

## Validations techniques

- 83 fichiers Python compilés ;
- `node --check static/app.js` réussi ;
- 20 fichiers YAML chargés avec PyYAML ;
- `git diff --check` réussi ;
- manifeste de release régénéré en version 4.6.0 ;
- aucun appel réel à The Odds API ;
- aucun crédit réel consommé ;
- aucun déploiement Railway réalisé depuis cet environnement.

## Fonctionnalités validées

- cockpit simple avec un seul panneau primaire visible ;
- persistance de l’onglet simple ;
- mode expert différé ;
- calibration football et tennis séparée ;
- holdout chronologique ;
- veto de non-dégradation ;
- registre stable `EXP-*` ;
- détection de feature future ;
- rapport de lineage ;
- endpoint Feature Lab sans fournisseur ;
- workflow Feature Lab à zéro crédit ;
- promotion automatique interdite.

## Limites

La V4.6 améliore l’évaluation de calibration et prépare les expériences. Elle ne revendique aucune rentabilité et ne remplace pas automatiquement les modèles sportifs. Les niveaux de fiabilité restent non évaluables tant que le volume live réglé est insuffisant.
