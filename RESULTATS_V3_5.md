# Résultats vérifiés V3.5

## Contrôles exécutés localement

- compilation Python : réussie ;
- syntaxe JavaScript : réussie ;
- tests : **91 réussis** ;
- endpoint `/api/health` : version `3.5.0` ;
- endpoint `/api/release` : version, release ID, modèle et intégrité disponibles ;
- endpoint `/api/system/status` : release, registre, base, shadow et benchmark consolidés ;
- manifeste de release : généré sans secret ;
- snapshot et rollback : testés sur fichiers temporaires ;
- registre de modèles : transitions et unicité du modèle actif testées ;
- backup/restore applicatif : testé entre deux bases SQLite distinctes ;
- métriques shadow : séparation par modèle/version/horizon testée.

## Non exécuté dans cet environnement

- déploiement réel Railway V3.5 ;
- vérification post-déploiement contre l’URL de production ;
- restauration vers une base PostgreSQL Railway de test ;
- appel The Odds API réel ;
- benchmark démontrant un avantage face à Winamax.

## Verdict statistique

Aucun changement : **NO-GO sur toute revendication de rentabilité** tant que l’échantillon shadow hors temps reste insuffisant.
