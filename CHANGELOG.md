# Changelog

## 3.3.0

- shadow mode automatique ;
- tables `shadow_predictions`, `model_registry`, `shadow_cycles` ;
- empreinte SHA-256 et contrôle temporel ;
- horizons `t-24h`, `t-6h`, `t-1h`, `pre-close` ;
- unicité par événement, modèle, version et horizon ;
- récupération ciblée des résultats ;
- règlement et métriques football ;
- registre de modèles multi-version ;
- détection du modèle périmé ;
- veto sur les sélections lorsque le modèle est trop ancien ;
- quota guard ;
- service cron Railway fini ;
- endpoints et interface shadow ;
- migration compatible depuis V3.2.1.

## 3.2.1

- correction de l’intervalle de confiance vide dans le frontend ;
- suppression du faux statut API indisponible.

## 3.2.0

- benchmark historique et worker de backfill.
