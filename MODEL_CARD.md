# Model Card V3.4

## Modèle actif livré

Le modèle actif de l'archive reste le modèle V3.3 construit sur le snapshot EPL 2023. Il est classé `degraded` et ses sélections opérationnelles sont bloquées.

## Candidat V3.4

Le pipeline peut entraîner un candidat sur les saisons 2021-22 à 2025-26 avec les caractéristiques suivantes : Elo, formes offensives/défensives, repos, taux de buts de ligue, Poisson/Dixon–Coles et CatBoost tabulaire.

## Validation

La séparation est chronologique et ne coupe pas les timestamps identiques. La calibration et le blend sont estimés sur une partition distincte. Le candidat doit passer les règles dans `PromotionPolicy` avant de remplacer l'artefact actif.

## Utilisation autorisée

- recherche personnelle ;
- comparaison probabiliste ;
- shadow mode ;
- audit de calibration.

## Utilisation refusée

- promesse de gains ;
- placement automatique ;
- taille de mise ;
- utilisation du candidat non promu comme modèle actif.
