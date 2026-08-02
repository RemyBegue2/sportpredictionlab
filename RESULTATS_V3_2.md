# Résultats vérifiés V3.2

## Contrôles exécutés

- 59 tests réussis ;
- couverture globale : 85,44 % ;
- couverture du moteur de benchmark marché : 87 % ;
- couverture du comparateur de cotes : 94 % ;
- compilation Python complète réussie ;
- syntaxe JavaScript validée ;
- endpoints santé, readiness, benchmark, qualité et backfills validés avec TestClient ;
- configurations Railway, cron, worker et Render analysées par les tests ;
- recherche de clé réelle : aucune clé embarquée.

## Benchmark réel

```text
status: not_run
evaluated_predictions: 0
profitability_claim: forbidden
```

Aucun appel historique réel n’a été effectué lors de la génération. Aucun crédit The Odds API n’a été consommé et aucun résultat de performance n’a été inventé.

## Résultats hérités du snapshot

Le modèle football snapshot reste utile pour vérifier l’application, mais ses métriques sur 20 matchs et son backtest externe sur 30 matchs ne constituent pas une preuve face à Winamax. Le modèle tennis reste Elo non calibré.

## Corrections V3.2 les plus importantes

1. Les snapshots historiques ne sont plus fusionnés par événement/bookmaker.
2. Un benchmark sans folds ne peut plus recevoir de verdict favorable.
3. Le plafond du worker tient compte du coût réel par requête planifiée.
4. Une réponse issue du cache ne consomme pas artificiellement le budget interne.
5. Les résultats récents peuvent être persistés et reliés aux événements connus.

## Prochaine donnée attendue

Le premier rapport significatif sera `artifacts/market_benchmark_v3_2.json`, produit localement ou par le worker après collecte réelle.
