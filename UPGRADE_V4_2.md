# Upgrade V4.2.0 — Coverage-Aware Evidence Planning

## Objectif

La V4.2 ajoute une étape obligatoire de préflight avant toute campagne historique payante. Elle répond au problème observé sur la campagne réelle V4.1 : la collecte technique était saine, mais la baseline consensus/Winamax n'était disponible que sur une faible fraction des matchs, après consommation de 264 crédits.

## Nouveautés

- workflow GitHub Actions `Estimate evidence coverage` ;
- verdict `VIABLE`, `RISKY` ou `NOT_VIABLE` ;
- matrice de couverture par bookmaker et par trimestre ;
- sondes plafonnées, reprenables et protégées contre les rejouements à facturation incertaine ;
- calcul du nombre d'événements à sélectionner pour atteindre le stage en événements benchmark-ready ;
- manifeste candidat immuable et hashé ;
- campagne payante bloquée sans préflight exact et viable ;
- expérience Pinnacle explicitement séparée de la comparaison Winamax/consensus ;
- endpoint `/api/coverage-preflight` et résumé dans le dashboard.

## Procédure

1. Fusionner et déployer la V4.2.0.
2. Vérifier `/api/ready` et `/api/release`.
3. Lancer `Estimate evidence coverage` avec un plafond de préflight limité.
4. Lire le rapport et la matrice de couverture.
5. Ne lancer `Run evidence campaign` que si le verdict est `VIABLE` et après approbation humaine.

## Compatibilité

Une campagne V4.1 sans préflight V4.2 ne peut pas être reprise comme campagne payante. Cette rupture est intentionnelle : elle empêche une reprise fondée sur un plan dont la disponibilité de baseline n'a pas été qualifiée.

## Invariants inchangés

- aucun pari automatique ;
- aucune recommandation de mise ;
- aucune promotion automatique ;
- aucune utilisation des résultats sportifs pour choisir les événements du préflight ou de la campagne ;
- le stage 100 reste interdit tant qu'un stage 30 réel n'affiche pas `PASS`.
