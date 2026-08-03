# Résultats de validation — V4.4.0

## Tests

- 219 tests collectés ;
- 219 tests réussis par lots disjoints ;
- 0 échec.

Lots validés :

- 20 tests : audit, backtest, betting et cloud ;
- 12 tests : entrées de déploiement ;
- 24 tests : frontend, Odds API et smoke ;
- 29 tests : sources, benchmark, shadow et rebuild ;
- 50 tests : evidence V3.5 à V3.9 ;
- 46 tests : campagne V4.0 à préflight V4.2 ;
- 38 tests : produit quotidien, laboratoire V4.4 et webapp.

La commande monolithique `pytest -q` a dépassé la limite de l'environnement d'audit. Les lots sont disjoints et couvrent l'intégralité des 219 tests collectés.

## Validations techniques

- compilation Python réussie ;
- syntaxe JavaScript validée avec Node ;
- workflows YAML et configurations Railway/Render analysés ;
- aucun appel réel à The Odds API ;
- aucune consommation de crédit ;
- aucun déploiement Railway depuis l'environnement de préparation.

## Fonctionnalités validées

- laboratoire football + tennis persistant ;
- capture payante manuelle et plafonnée ;
- obligation du mode shadow avant toute capture ;
- règlement des résultats football et tennis ;
- simulations de bankroll 100, 500 et 1 000 avec trois stratégies ;
- politique ROI sur blocs chronologiques et holdout ;
- méta-modèle logistique portable ;
- une seule observation par événement pour l'entraînement ;
- réhabilitation tennis impossible avant preuve spécifique au sport ;
- dashboard sans appel fournisseur ;
- invariants no-bet et no-stake.

## Limites

Aucun ROI réel n'est revendiqué. Les simulations ne deviennent évaluables qu'après au moins 30 événements réglés pour la politique et 60 pour le méta-modèle. Le tennis reste normalement en abstention avant une preuve suffisante spécifique au tennis.
