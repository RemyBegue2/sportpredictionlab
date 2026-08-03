# Résultats vérifiés — V4.1

Date de validation : 3 août 2026.

## Validation du code

- 155 tests collectés et réussis par quatre lots : 32 + 26 + 41 + 56 ;
- aucun échec ;
- couverture du cœur `sports_predictor` + `webapp` : 83 % ;
- compilation Python réussie ;
- syntaxe JavaScript de `static/app.js` réussie ;
- 12 fichiers YAML parsés avec succès ;
- vérification de cohérence des sondes `/api/ready` ;
- vérification du verrou commun `production-change`.

## Régressions V4.1 couvertes

- impossibilité de contourner le stage suivant avec `continue_current_stage` ;
- reprise autorisée uniquement pour la campagne exacte ;
- porte spécifique à la baseline ;
- fin explicite après le stage 1 000 ;
- matching bijectif et collisions mises en quarantaine ;
- consensus refusé avec un seul bookmaker indépendant ;
- progression fondée sur les événements uniques prêts pour benchmark ;
- total des crédits découverte + snapshots ;
- checkpoint conservé après une interruption de découverte ;
- restauration possible avant la création du backfill ;
- `HOLD` pour une collecte incomplète et `FAIL` pour une corruption d’intégrité ;
- rejeu d’un appel incertain uniquement sur option explicite ;
- publication d’un rapport `HOLD` lorsqu’une découverte terminée ne renvoie aucun événement ;
- permission `actions: read` explicite pour restaurer les checkpoints GitHub.

## Ce qui n’a pas été exécuté

- aucun appel réel à The Odds API ;
- aucun crédit fournisseur consommé ;
- aucun workflow exécuté sur le dépôt GitHub de l’utilisateur ;
- aucun déploiement Railway réalisé ;
- aucune preuve réelle de stage 30 produite avec la V4.1.

Le résultat valide donc le code préparé, pas l’état de production.
