# Risques et portes — V4.5.0

## Portes avant automatisation payante

1. V4.5.0 déployée et `/api/ready` au vert.
2. Vue simple rendue sans erreur navigateur.
3. Produit modèle seul opérationnel.
4. `DAILY_ODDS_ENABLED=true` uniquement pendant l’expérience approuvée.
5. `SHADOW_MODE_ENABLED=true`.
6. `AUTOMATED_SHADOW_ENABLED=true` dans Railway et variable GitHub du même nom.
7. `DAILY_ODDS_MAX_CREDITS` et `AUTOMATED_SHADOW_MAX_CREDITS` entre 1 et 3.
8. `HISTORICAL_EVIDENCE_ENABLED=false`.

## Portes avant promotion

- au moins 100 événements réglés au total ;
- au moins 60 événements football et 60 tennis ;
- au moins 20 signaux dans le holdout ;
- politique et méta-modèle `candidate` ;
- au moins trois folds évaluables ;
- au moins 60 % de folds non négatifs ;
- drawdown holdout inférieur ou égal au plafond pré-enregistré ;
- challenger non dégradé face au champion lorsqu’un champion existe ;
- revue humaine et confirmation `PROMOTE_RESEARCH_CHAMPION`.

## Risques P1

- petit échantillon live et variance élevée du ROI ;
- disponibilité variable des marchés tennis ;
- baseline tennis non calibrée ;
- dépendance aux horaires et résultats fournisseur ;
- actions GitHub non toutes figées par SHA immuable ;
- absence d’Alembic avant une future migration complexe ;
- rate limiter local au processus ;
- rétention des preuves limitée par la politique opérationnelle.

## Hors périmètre

- mise réelle ou personnalisée ;
- placement automatique ;
- connexion bookmaker ;
- martingale ;
- promotion automatique ;
- promesse de rentabilité ;
- optimisation in-sample des modèles sportifs ;
- réactivation des campagnes historiques.
