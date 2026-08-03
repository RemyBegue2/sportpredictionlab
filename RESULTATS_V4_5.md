# Résultats de validation — V4.5.0

## Tests

- 235 tests collectés ;
- 235 tests réussis ;
- 0 échec ;
- exécution par lots disjoints pour respecter la limite de l’environnement.

Lots validés :

- 32 tests : audit, backtest, betting, cloud et déploiement ;
- 22 tests : frontend et connecteur de cotes ;
- 31 tests : smoke, sources, benchmark, shadow et rebuild ;
- 50 tests : evidence V3.5 à V3.9 ;
- 29 tests : campagne V4.0, intégrité V4.1 et hotfix frontend ;
- 51 tests : préflight V4.2, produit quotidien V4.3 et laboratoire V4.4 ;
- 20 tests : automatisation V4.5 et webapp.

## Couverture

Mesure avec branches sur les lots exécutables :

- couverture combinée instructions/branches : **78,3 %** ;
- couverture des instructions : **83,0 %** ;
- `database.py` : **83 %** ;
- `cloud_config.py` : **76 %** ;
- `control_center.py` : **73 %** ;
- `webapp.py` : **66 %** avec branches.

Un lot V4.4 complet sous instrumentation coverage a terminé ses assertions mais n’a pas quitté proprement avant la limite de l’environnement. Ses tests ont été validés séparément sans instrumentation ; aucune couverture issue de ce processus interrompu n’a été revendiquée.

## Validations techniques

- compilation de tous les modules Python réussie ;
- `node --check static/app.js` réussi ;
- workflows et configurations YAML chargés avec PyYAML ;
- version Python/package : 4.5.0 / 0.4.5.0 ;
- cache frontend : `app.js?v=4.5.0` ;
- aucun appel réel à The Odds API ;
- aucun crédit réel consommé ;
- aucun déploiement Railway depuis l’environnement de préparation.

## Fonctionnalités validées

- vue simple par défaut ;
- mode expert persistant et chargé à la demande ;
- panneau champion/challenger ;
- budget quotidien partagé ;
- capture automatisée bloquée sans feature flag ;
- journée vide sans appel football payant ;
- règlement no-op à zéro crédit ;
- optimisation hebdomadaire sans fournisseur ;
- portes de promotion par sport et holdout ;
- promotion manuelle uniquement ;
- trajectoire de bankroll fictive ;
- invariants no-bet et no-stake.
