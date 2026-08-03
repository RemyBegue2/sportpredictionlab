# Résultats de validation — V4.3.0

## Tests

- 205 tests collectés ;
- 205 tests réussis ;
- 0 échec ;
- exécution en cinq lots disjoints : 27 + 40 + 53 + 73 + 12.

## Couverture

La mesure finale a été exécutée avec couverture de branches :

- couverture des instructions : **82,4 %** ;
- couverture combinée instructions/branches : **78 %** ;
- `webapp.py` : environ **79,6 %** des instructions, **76 %** avec branches ;
- `daily_product.py` : environ **71,0 %** des instructions, **67 %** avec branches.

## Validations techniques

- compilation Python réussie ;
- syntaxe JavaScript validée avec Node ;
- 14 fichiers YAML validés ;
- routes locales `/api/model-diagnostics`, `/api/credit-firewall` et `/api/daily/slate` exécutées ;
- pare-feu confirmé à zéro crédit par défaut ;
- rendu quotidien et comportement frontend couverts par tests Node et smoke Chromium intégré au workflow ;
- aucun appel réel à The Odds API pendant la préparation.

## Diagnostic du modèle embarqué

- état : `operational_research` ;
- version : `3.4.0-fresh` ;
- registre : `shadow` ;
- cutoff des données : 2026-05-24 ;
- test chronologique : 380 observations ;
- log-loss modèle : 1,0619 ;
- log-loss baseline naïve : 1,0846 ;
- ECE : 0,0959 ;
- probabilités modèle seules : disponibles ;
- shortlist marché : non validée.

## Limites de validation

L’environnement de préparation n’a pas permis de confirmer la connectivité sortante réelle vers ESPN ou Football-Data. Les parseurs, caches, replis et erreurs sont testés avec des réponses représentatives. Aucun déploiement Railway ou run GitHub réel n’a été effectué depuis cet environnement.
