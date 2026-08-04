# Risques et portes — V4.8.0

## Portes dataset tennis

### Exploration

- 500 matchs acceptés ;
- 50 dates distinctes ;
- au moins deux surfaces suffisamment couvertes ;
- quarantaine sous le plafond ;
- aucune feature future.

### Challenger

- 1 500 matchs acceptés ;
- 150 dates distinctes ;
- au moins deux surfaces avec 200 matchs chacune ;
- licence `research_only` ou `approved` ;
- lineage complète pour un dataset de promotion ;
- holdout scellé et distinct.

État livré : **32 matchs, deux dates, `collecting`**.

## Portes football

- dataset reproductible ;
- train, calibration et holdout chronologiques ;
- amélioration du log loss d’au moins 0,002 ;
- ECE non dégradée de plus de 0,015 ;
- stabilité sur plusieurs sous-groupes ;
- maximum deux challengers au prochain tour ;
- aucune optimisation directe sur le ROI ;
- promotion humaine uniquement.

État livré : **`hold_explained`**, delta log loss approximatif **+0,0307** face à la baseline.

## Portes longue session

- durée recommandée : 1 800 secondes ;
- aucune erreur JavaScript ;
- aucun toast d’interface partielle ;
- un seul panneau simple actif ;
- DOM sans croissance supérieure au seuil ;
- requêtes sans croissance non bornée ;
- chargement expert non dupliqué ;
- rapport JSON publié.

Le workflow existe mais doit encore être exécuté contre la production publique.

## Portes plateforme

- migration Alembic appliquée avant le démarrage ;
- nouvelles tables présentes ;
- downgrade testé hors production ;
- toute action GitHub référencée par SHA complet ;
- artefacts et datasets hashés ;
- fournisseur absent des workflows d’entraînement.

## Risques P1 résiduels

- historique tennis réel insuffisant ;
- lineage incomplète des anciens imports ;
- test longue session public non encore exécuté ;
- rate limiter toujours local au processus ;
- rétention des preuves dépendante de la politique opérationnelle ;
- futurs challengers football encore à évaluer.

## Hors périmètre

- pari réel ou personnalisé ;
- placement automatique ;
- connexion bookmaker ;
- martingale ;
- promotion automatique ;
- optimisation ROI in-sample ;
- nouveaux marchés ou nouvelles ligues ;
- données historiques payantes pour l’entraînement.
