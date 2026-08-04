# Risques et portes — V4.9.0

## Portes football

### Développement

- maximum deux challengers ;
- train, calibration et validation chronologiques ;
- aucune ligne du holdout consulté utilisée pour sélectionner les modèles ;
- amélioration du log loss d’au moins 0,002 ;
- ECE non dégradée de plus de 0,015 ;
- aucune régression supérieure à 0,020 sur les sous-groupes protégés ;
- paramètres portables ;
- zéro crédit fournisseur.

### Promotion

- nouvelle génération de holdout ;
- au moins 30 nouvelles dates distinctes après le cutoff ;
- aucune modification du modèle après consultation ;
- comparaison au champion ;
- revue humaine ;
- rollback disponible.

État livré : deux challengers `hold`, nouvelle génération `open_collecting`.

## Portes tennis

### Exploration

- 500 matchs ;
- 50 dates ;
- plusieurs surfaces suffisamment couvertes ;
- quarantaine sous le plafond ;
- aucune feature future.

### Challenger

- 1 500 matchs ;
- 150 dates ;
- au moins deux surfaces avec 200 matchs chacune ;
- licence acceptable ;
- lineage complète ;
- holdout distinct et scellé.

État livré : 32 matchs, deux dates, entraînement bloqué.

## Portes production

- scénario simple `status = ok` ;
- scénario expert `status = ok` ;
- aucune erreur console ou page ;
- un seul panneau actif ;
- croissance DOM sous le seuil ;
- aucune croissance réseau non bornée ;
- aucun chargement expert dupliqué ;
- version 4.9.0.

État livré : workflows prêts, preuves publiques non exécutées.

## Risques P1 résiduels

- futur holdout football encore vide ;
- historique tennis réel insuffisant ;
- lineage partielle des anciens imports ;
- sessions longues publiques non exécutées ;
- rate limiter local au processus ;
- rétention des datasets et rapports dépendante de la politique opérationnelle.

## Hors périmètre

- pari réel ou personnalisé ;
- placement automatique ;
- connexion bookmaker ;
- martingale ;
- promotion automatique ;
- optimisation ROI in-sample ;
- nouveaux marchés ou nouvelles ligues ;
- données historiques payantes pour l’entraînement.
