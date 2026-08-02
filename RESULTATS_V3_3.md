# Résultats vérifiés — V3.3

## État de livraison

- version API : 3.3.0 ;
- shadow mode : implémenté ;
- PostgreSQL : nouvelles tables compatibles avec la migration V3.2.1 ;
- cron Railway : configuration fournie ;
- placement automatique : absent ;
- appels réels The Odds API pendant la construction : 0 ;
- résultats shadow réels : 0 au moment du packaging ;
- tests : 71 réussis ;
- couverture globale : 85 % ;
- couverture shadow : 86 % ;
- couverture persistance : 89 % ;
- couverture cron : 81 %.

## Modèle football embarqué

- 90 matchs EPL ;
- période : 11 août 2023 au 23 octobre 2023 ;
- test interne : 20 matchs ;
- backtest externe : 30 matchs, un seul fold ;
- poids ML retenu : 0 ;
- modèle servi : composante Poisson/Dixon–Coles ;
- statut V3.3 pour une fixture 2026 : `degraded_stale`.

Les métriques historiques restent des tests de fumée, pas une validation actuelle.

## Modèle tennis

- 32 lignes ;
- deux timestamps de tournoi ;
- calibration valide impossible ;
- mode servi : Elo non calibré ;
- statut : expérimental ;
- promotion : interdite.

## Shadow mode

Métriques produites après règlement :

- log-loss ;
- Brier ;
- RPS ;
- accuracy ;
- résultat fictif à une unité pour les candidats ;
- maturité de l’échantillon ;
- agrégats séparés par horizon.

Aucune valeur réelle n’est annoncée ici, car aucun cycle avec la clé de l’utilisateur n’a été exécuté dans cet environnement.

## Conclusion

Le résultat démontré par la V3.3 est une capacité de collecte et d’audit, pas un avantage sportif. Le premier enseignement opérationnel attendu sera probablement la faiblesse d’un modèle 2023 appliqué à 2026 ; cette information est utile et doit conduire au réentraînement plutôt qu’à la dissimulation.
