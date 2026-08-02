# Model card — Sports Prediction Lab V3.1 Cloud

## Modification par rapport à la V3.0

La V3.1 modifie le **serving**, le stockage et la sécurité. Elle ne change pas les modèles statistiques embarqués et ne publie aucune nouvelle mesure de performance.

## Football

- données snapshot EPL 2023-2024 ;
- Elo et forme pré-match ;
- buts CatBoost Poisson ;
- correction Dixon–Coles ;
- calibration et blend gardés par validation ;
- modèle ML rejeté dans le snapshot livré (`ml_blend_weight=0`) ;
- usage limité à la recherche.

## Tennis

- petit snapshot ATP 2025 ;
- Elo global et surface ;
- seulement deux timestamps de tournoi distincts ;
- aucune calibration valide possible ;
- service `elo_only_uncalibrated` ;
- abstention normale dès qu'une décision de marché est demandée.

## Contrôles de serving V3.1

- aucune date antérieure au cutoff ;
- aucune analyse après le début du match ;
- marchés complets seulement ;
- cote horodatée ;
- journal de version du modèle ;
- échec si le journal ne peut être écrit ;
- cote devenue ancienne reclassée à l'affichage.

## Usages interdits

- garantie de gain ;
- automatisation des mises ;
- taille de mise ou gestion de bankroll ;
- usage public sans revue de sécurité et conformité ;
- interprétation du snapshot comme preuve de rentabilité.
