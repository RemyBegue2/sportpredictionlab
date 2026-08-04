# Résultats de validation — V4.8.0

## Tests

- **261 tests collectés** ;
- **261 tests réussis** ;
- **0 échec** ;
- exécution en six lots disjoints : `54 + 31 + 50 + 46 + 60 + 20`.

La suite monolithique n’est pas utilisée comme preuve, car certaines versions de l’environnement ont déjà gardé des processus ouverts après la fin des assertions. Chaque fichier de test appartient à un seul lot et les 261 tests collectés sont tous couverts.

## Couverture ciblée

Lot instrumenté : V4.7, V4.8 et webapp.

- `sports_predictor/evidence_acceleration.py` : **94 %** combiné branches/instructions ;
- `sports_predictor/challenger_factory.py` : **90 %** ;
- 20 tests instrumentés réussis.

## Preuves produites

### Football

- dataset : 1 900 matchs, 583 dates ;
- entraînement : 1 106 lignes ;
- calibration : 401 lignes ;
- holdout : 393 lignes ;
- delta log loss challenger–baseline : environ **+0,0307** ;
- régressions principales : nul, repos déséquilibré, victoire extérieure ;
- verdict : `hold_explained` ;
- champion non remplacé.

### Tennis

- archive livrée : 32 matchs ;
- deux dates distinctes ;
- import normalisé et hashé ;
- statut : `collecting` ;
- aucune preuve artificielle produite.

## Validations plateforme

- compilation de 86 fichiers Python ;
- syntaxe `static/app.js` validée avec Node ;
- 22 workflows GitHub chargés avec PyYAML ;
- Render YAML et quatre fichiers TOML validés ;
- migration Alembic upgrade/downgrade vérifiée ;
- toutes les références `actions/*` vérifiées comme SHA complets ;
- release manifest généré en version 4.8.0 ;
- archive finale extraite et 16 tests critiques réexécutés ;
- patch appliqué sur une copie propre de la V4.7.0 ;
- aucun appel réel à The Odds API ;
- aucun crédit réel consommé ;
- aucun déploiement Railway effectué.

## Interface

- exactement trois onglets simples ;
- un seul panneau actif ;
- carte `À retenir` dans Aujourd’hui ;
- huit cartes maximum par liste ;
- Evidence Acceleration rendu dans Apprentissage ;
- mode expert chargé à la demande ;
- test longue session configurable et rapport JSON.

## Limite décisive

Le workflow public de 30 minutes est fourni, mais il n’a pas été exécuté contre l’application publique depuis l’environnement de préparation. Il reste la validation décisive de la stabilité réelle du navigateur et du réseau en production.
