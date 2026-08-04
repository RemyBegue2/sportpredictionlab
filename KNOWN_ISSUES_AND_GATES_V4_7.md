# Risques et portes — V4.7.0

## Portes Challenger Factory

- dataset hashé et reproductible ;
- minimum 120 lignes ;
- minimum 12 dates distinctes ;
- split chronologique train/calibration/holdout ;
- holdout jamais utilisé pour entraîner ;
- log loss amélioré d’au moins 0,002 face à la baseline ;
- ECE non dégradée de plus de 0,015 ;
- paramètres portables ;
- zéro crédit fournisseur ;
- promotion manuelle uniquement.

## État réel livré

- football : 1 900 matchs, challenger entraîné, verdict `hold` ;
- tennis : 32 matchs, 2 dates, statut `collecting` ;
- aucun modèle sportif remplacé ;
- aucun ROI revendiqué.

## Portes de stabilité UI

- un seul panneau simple actif ;
- huit cartes maximum par liste simple ;
- GET identiques dédupliqués ;
- timeout réseau de 12 secondes ;
- requêtes annulées à la fermeture ;
- mode expert réessayable après échec partiel ;
- aucune erreur JavaScript ou interface partielle dans le smoke test ;
- navigation répétée sans accumulation de panneaux actifs.

## Risques P1

- historique tennis réel insuffisant et peu diversifié ;
- challenger football non supérieur au champion ;
- actions GitHub encore majoritairement référencées par tags ;
- Alembic absent avant une modification complexe du schéma ;
- rate limiter local ;
- smoke longue session public non exécuté depuis l’environnement d’audit ;
- rétention limitée des artefacts et preuves.

## Hors périmètre

- pari réel ou personnalisé ;
- placement automatique ;
- connexion bookmaker ;
- martingale ;
- promotion automatique ;
- optimisation des modèles sur le ROI in-sample ;
- nouveaux marchés ou ligues ;
- consommation de crédits pour l’entraînement.
