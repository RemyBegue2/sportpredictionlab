# Model Card — V3.2

## Usage prévu

Recherche probabiliste pré-match, comparaison aux marchés et audit de calibration. Pas de conseil financier, pas de mise automatique et pas de garantie de rendement.

## Football

- Elo et forme séquentielle ;
- CatBoost Poisson pour les buts ;
- correction Dixon–Coles ;
- classifieur 1N2 calibré ;
- prédiction par groupes de timestamps identiques ;
- walk-forward externe pour le benchmark V3.2.

Le modèle snapshot livré n’est pas refitté sur un corpus multi-saisons complet. Il sert principalement au fonctionnement de l’application.

## Tennis

Mode livré : Elo global/surface non calibré. Aucune promotion analytique autorisée.

## Marché

Les cotes sont déviguées avant comparaison. Winamax est séparé du consensus. Le blend modèle/consensus apprend son poids sur le train de chaque fold seulement.

## Critères de promotion

- folds chronologiques disponibles ;
- au moins 500 prédictions hors échantillon par défaut ;
- intégrité temporelle ;
- matching fiable ;
- amélioration probabiliste robuste contre Winamax ;
- résultats non concentrés sur une courte période ;
- CLV observée comme signal secondaire.

## État actuel

`not_run` pour le benchmark historique réel.
