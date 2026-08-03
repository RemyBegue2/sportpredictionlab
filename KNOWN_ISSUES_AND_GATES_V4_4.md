# Risques et portes — V4.4.0

## Portes avant une capture live

1. V4.4.0 déployée et `/api/ready` au vert.
2. Produit quotidien modèle seul opérationnel.
3. `DAILY_ODDS_ENABLED=true` uniquement pour la fenêtre de capture.
4. `DAILY_ODDS_MAX_CREDITS` fixé à un petit entier, recommandé : 3.
5. `SHADOW_MODE_ENABLED=true`.
6. Confirmation humaine `CAPTURE_DAILY_MARKET`.
7. Campagnes historiques toujours désactivées.

## Portes statistiques

- moins de 30 événements réglés : politique ROI non évaluable ;
- moins de 60 événements réglés : méta-modèle non évaluable ;
- moins de 30 événements d'un sport : le méta-modèle ne peut pas réhabiliter une abstention de ce sport ;
- moins de 5 signaux sur le holdout : politique classée non évaluable ;
- toute fuite temporelle ou incohérence de résultat invalide l'observation.

## Risques P1

- disponibilité variable des bookmakers et tournois tennis ;
- modèle tennis de base non calibré ;
- variance très élevée du ROI à petit échantillon ;
- sélection de politique parmi 144 candidats pouvant encore sur-ajuster un petit développement set ;
- actions GitHub non toutes figées par SHA ;
- absence d'Alembic ;
- stockage des preuves limité par la rétention opérationnelle.

## Hors périmètre

- mise réelle ou personnalisée ;
- placement automatique ;
- connexion à un compte bookmaker ;
- martingale ou récupération de pertes ;
- promotion automatique ;
- promesse de rentabilité ;
- optimisation des modèles sportifs directement sur le ROI in-sample.
