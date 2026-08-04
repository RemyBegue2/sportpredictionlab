# Risques et portes — V4.6.0

## Portes avant candidat de calibration

- au moins 30 événements réglés pour le sport ;
- groupes chronologiques suffisants ;
- holdout d’au moins 8 événements ;
- aucune violation temporelle du manifeste ;
- log loss holdout non dégradé de plus de 0,002 ;
- ECE holdout non dégradée de plus de 0,015 ;
- paramètres portables ;
- zéro appel fournisseur.

## Portes avant promotion du champion

Les portes V4.5 restent inchangées :

- 100 événements réglés au total ;
- 60 football et 60 tennis ;
- 20 signaux holdout ;
- trois folds évaluables ;
- 60 % de folds non négatifs ;
- drawdown sous le plafond ;
- non-dégradation face au champion ;
- revue humaine.

Un calibrateur `candidate` ne suffit pas à promouvoir un champion.

## Risques P1

- faible volume live réglé ;
- baseline tennis encore limitée ;
- anciennes observations sans feature manifest ;
- actions GitHub encore majoritairement référencées par tags ;
- Alembic absent avant une future migration complexe ;
- rate limiter local ;
- rétention limitée des preuves.

## Hors périmètre

- pari réel ou personnalisé ;
- placement automatique ;
- promotion automatique ;
- optimisation du modèle sur ROI in-sample ;
- nouveaux marchés ou ligues ;
- réactivation des campagnes historiques ;
- consommation de crédits pour le Feature Lab.
