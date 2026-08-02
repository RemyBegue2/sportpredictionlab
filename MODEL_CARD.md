# Model Card — V3.6

## Usage prévu

Recherche privée sur probabilités pré-match football 1N2. Le modèle champion est comparé à Winamax, au consensus et à un blend 50/50. Le système n’exécute aucun pari.

## Statut

Le statut opérationnel est conservé dans le registre PostgreSQL. La V3.6 n’effectue aucune promotion automatique. Un verdict `promotion_review` demande une validation humaine.

## Évaluation

Métriques principales : log-loss, Brier, RPS, ECE, stabilité par folds chronologiques, différence appariée au consensus et CLV. Les résultats sont séparés par horizon.

## Seuils par défaut

- signal exploratoire : 200 observations historiques ;
- revue sérieuse : 1 000 observations historiques ;
- live shadow : 200 observations réglées au même horizon ;
- intervalle à 95 % favorable face au consensus ;
- majorité des folds favorable ;
- calibration non dégradée ;
- CLV médiane non négative.

## Limites

Aucun benchmark historique réel n’a été exécuté dans le paquet V3.6 livré. Les seuils sont des portes de gouvernance, pas une garantie de performance future.
