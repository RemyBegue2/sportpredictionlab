# Résultats de validation — V4.7.0

## Tests

- 253 tests collectés ;
- 253 tests réussis ;
- 0 échec ;
- exécution en cinq lots disjoints : 47 + 38 + 50 + 46 + 72.

## Couverture ciblée

Lot instrumenté : V4.5, V4.6, V4.7 et webapp.

- `sports_predictor/challenger_factory.py` : **90 %** combiné branches/instructions ;
- 38 tests instrumentés réussis ;
- la couverture ciblée complète les cinq lots fonctionnels et ne les remplace pas.

## Challenger Factory réelle

### Football

- archive locale : 1 900 matchs ;
- 583 dates distinctes ;
- entraînement : 1 106 lignes ;
- calibration : 401 lignes ;
- holdout : 393 lignes ;
- modèle : régression logistique multinomiale régularisée ;
- log loss holdout challenger : environ 1,0522 ;
- ECE holdout challenger : environ 0,0782 ;
- verdict : `hold` ;
- aucun remplacement du champion.

### Tennis

- archive livrée : 32 matchs ;
- 2 dates distinctes ;
- seuil : 120 lignes et 12 dates ;
- verdict : `collecting` ;
- le pipeline surface-aware a été validé par test multi-surface mais aucune preuve réelle n’est inventée.

## Validations frontend

- GET concurrents identiques dédupliqués dans Node ;
- timeout réseau et annulation des requêtes présents ;
- un seul toast actif ;
- mode expert mutualisé et réessayable ;
- huit cartes maximum par liste simple ;
- navigation longue session ajoutée au smoke Chromium ;
- syntaxe JavaScript validée avec Node.

## Validations techniques

- 83 fichiers Python compilés ;
- 21 fichiers YAML analysés avec PyYAML, dont 20 workflows ;
- manifeste de release régénéré en version 4.7.0 ;
- intégrité des artefacts existants validée ;
- aucune occurrence `railway up --ci` ;
- aucun appel réel à The Odds API ;
- aucun crédit réel consommé ;
- aucun déploiement Railway depuis l’environnement de préparation.

## Limites

Le smoke Chromium a été renforcé mais n’a pas été exécuté contre le déploiement public depuis cet environnement. Le challenger football reste en `hold` et l’historique tennis réel reste insuffisant. Aucune rentabilité n’est revendiquée.
