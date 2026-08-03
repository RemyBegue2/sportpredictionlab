# Model Card — V3.7

## Usage prévu

Recherche privée sur probabilités pré-match football 1N2. Le modèle champion est comparé à Winamax, au consensus et à un blend 50/50. Le système n’exécute aucun pari.

## Statut

Le statut opérationnel est conservé dans le registre PostgreSQL. La V3.7 n’effectue aucune promotion automatique. Un verdict `promotion_review` demande une validation humaine.

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

Aucun benchmark historique réel n’a été exécuté dans le paquet V3.7 livré. Les seuils sont des portes de gouvernance, pas une garantie de performance future.

## V3.8 — usage de la preuve

La V3.8 ne modifie pas le modèle football. Elle ajoute un protocole de collecte et de qualité destiné à déterminer si le modèle mérite une analyse plus large.

Une porte `technical_validation` indique seulement que la chaîne fonctionne sur un petit échantillon. Elle ne signifie ni avantage statistique ni rentabilité.

## V4.3 daily-product status

The football model is exposed for **model-only research probabilities**, not for automatic betting decisions. The V4.3 runtime checks artifact integrity, a valid probability vector, chronological test size, log-loss against a naive baseline, calibration availability and model freshness.

Current bundled metrics at preparation time:

- model version: `3.4.0-fresh`;
- chronological test observations: 380;
- log-loss: 1.0619;
- naive log-loss: 1.0846;
- ECE: 0.0959;
- market-shortlist readiness: false;
- automatic betting and staking: false.

A valid model-only prediction may be displayed without odds. A market shortlist requires separate live-market evidence and remains disabled by default.
