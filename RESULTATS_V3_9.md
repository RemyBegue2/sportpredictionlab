# Résultats de validation V3.9

## Validation exécutée

```text
135 tests réussis
0 échec
10 workflows YAML chargés avec succès
syntaxe JavaScript valide
compilation Python valide
```

## Régression principale

Scénario contrôlé :

```text
111 événements découverts
30 demandés
10 sélectionnés et exécutés
10 retournés
3 avec Winamax
10 avec au moins deux bookmakers complets
```

Résultat attendu et vérifié :

```text
couverture fournisseur : 100 %
couverture Winamax : 30 %
couverture consensus : 100 %
dénominateur planned_events : 10
porte globale : validation technique, pas conclusion statistique
```

Ce scénario vérifie la formule, pas les valeurs exactes de la production. Les valeurs exactes seront produites par **Recompute latest evidence** à partir de l’artefact du vrai run.

## Contrôles supplémentaires

- les nouveaux plans écrivent un statut de sélection par événement ;
- un événement non sélectionné par le budget n’est pas un échec fournisseur ;
- le matching est filtré sur les événements retournés ;
- Winamax et consensus ont des portes séparées ;
- un ancien rapport V3.8 est masqué jusqu’au recalcul ;
- le workflow de recalcul ne contient aucune référence à `THE_ODDS_API_KEY` ;
- aucun accès PostgreSQL n’est nécessaire pour le recalcul ;
- le déploiement est vérifié après publication.

## Limites de la validation

- aucun accès au dépôt GitHub de l’utilisateur depuis cet environnement ;
- aucun appel au vrai abonnement The Odds API ;
- aucun déploiement vers le projet Railway de l’utilisateur ;
- la récupération du vrai artefact sera testée par le workflow GitHub ;
- si l’artefact historique a expiré, le recalcul s’arrêtera sans consommer de crédit.
