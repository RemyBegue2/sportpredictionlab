# Analyse de campagne — CMP-7DD3582E9007344F9F9F500A

## Verdict

`HOLD` légitime. La chaîne technique a fonctionné, mais la preuve statistique demandée n'est pas disponible avec cet échantillon de bookmakers.

## Résultats utiles

- 30 événements demandés et sélectionnés.
- 29 snapshots retournés et acceptés par le fournisseur.
- 28 événements appariés de manière fiable.
- aucune fuite temporelle, aucun doublon, aucune collision de matching.
- couverture fournisseur : 96,7 %.
- couverture Pinnacle : 96,7 %.
- couverture Winamax, Betclic et Unibet : 23,3 % chacun.
- couverture PMU : 20 %.
- 7 événements disposent d'un consensus éligible.
- 6 événements seulement sont prêts pour le benchmark.
- 264 crédits consommés sur 350.

## Lecture multi-rôles

### Data / fournisseur

Le fournisseur a bien retourné presque tous les matchs, mais essentiellement via Pinnacle. Le problème n'est pas le téléchargement général : c'est l'absence historique des bookmakers français demandés sur la majorité des dates sélectionnées.

### Statisticien

Six lignes ne permettent pas de former un fold chronologique expanding-window. Les écarts descriptifs de log loss ne doivent pas être interprétés comme une supériorité du modèle.

### FinOps

Le plan est terminé : 25 requêtes sur 25 ont été exécutées. Une reprise du même plan ne peut pas créer les 23 événements de consensus manquants. Les 86 crédits restants ne doivent pas être consommés sans nouveau plan de couverture.

### Produit

Le stage 30 n'est pas validé, mais l'expérience a produit une conclusion utile : l'échantillonnage uniforme 2023–2026 n'est pas compatible avec l'objectif de comparaison Winamax/consensus français via ces données historiques.

## Action recommandée

Ne pas exécuter `continue_current_stage` et ne pas démarrer le stage 100.

La prochaine évolution doit ajouter un **coverage preflight** peu coûteux qui :

1. sonde la disponibilité réelle des bookmakers par période ;
2. estime le nombre d'événements Winamax et consensus avant le backfill complet ;
3. refuse une campagne dont la couverture projetée ne peut pas atteindre 70 % ;
4. choisit ensuite une fenêtre temporelle compatible, sans optimiser sur les résultats sportifs.

Une baseline Pinnacle pourrait être ajoutée comme expérience séparée, mais elle ne répondrait pas à la question Winamax et ne doit pas remplacer silencieusement la baseline actuelle.
