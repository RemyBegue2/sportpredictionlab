# Résultats vérifiés — V3.8

## Validation locale de l'upgrade

```text
117 tests réussis
0 test échoué
83 % de couverture du package sports_predictor
syntaxe Python valide
syntaxe JavaScript valide
workflows YAML valides
```

## Contrats vérifiés

- estimation déterministe et sans appel fournisseur ;
- identifiant `REQ-...` modifié dès qu'un paramètre change ;
- plafonds de 30 événements, 31 appels de découverte et 200 crédits ;
- Winamax obligatoire dans le lot contrôlé ;
- rejet des snapshots à l'heure du match ou après ;
- blocage en présence de fuite temporelle ;
- absence d'affirmation de rentabilité ;
- endpoint `/api/evidence` ;
- rendu frontend de la porte qualité ;
- workflows entièrement déclenchables depuis GitHub ;
- déploiement Railway et vérification de release après publication du rapport.

## Ce qui n'a pas été exécuté ici

- aucun appel réel à The Odds API ;
- aucun crédit consommé ;
- aucun déploiement sur le Railway de l'utilisateur ;
- aucun benchmark réel produit ;
- aucune promotion de modèle.

Ces opérations exigent les secrets et le projet cloud de l'utilisateur et sont volontairement accessibles depuis GitHub Actions.
