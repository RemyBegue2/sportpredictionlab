# Roadmap après V3.1

## V3.1 Cloud — livrée

- déploiement Railway/Render ;
- PostgreSQL ;
- authentification et CSRF ;
- cron de cotes ;
- journal des prédictions ;
- page quotidienne alimentée par la base ;
- contrôle de fraîcheur ;
- health/readiness ;
- 41 tests.

## V3.2 — benchmark historique réel

1. Collecter EPL sur plusieurs saisons avec budget validé.
2. Capturer 24 h, 6 h, 1 h et closing 10 min.
3. Appairer résultats, modèle, Winamax et consensus.
4. Exécuter cinq folds expanding-window.
5. Choisir les seuils uniquement dans les folds d'entraînement.
6. Mesurer log-loss, Brier, RPS, calibration, couverture et CLV.
7. Produire des intervalles par block bootstrap.
8. Geler une règle de sélection avant le dernier fold.
9. Publier aussi les segments où le modèle perd contre le marché.

## V3.3 — durcissement cloud

- Alembic ;
- Redis pour rate limiting et verrou de cron ;
- alertes quota et fraîcheur ;
- sauvegarde et test de restauration ;
- métriques Prometheus/OpenTelemetry ;
- filtre d'historique ;
- comptes individuels/MFA seulement si plusieurs utilisateurs ;
- format d'artefact signé ou plus sûr.

## V3.4 — extension de données

- Ligue 1, Liga, Bundesliga et Serie A ;
- identités canoniques versionnées ;
- WTA et ATP avec timestamps exacts ;
- modèle tennis calibré uniquement après données suffisantes ;
- comparaison par ligue, surface et horizon.
