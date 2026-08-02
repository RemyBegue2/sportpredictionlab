# Risques et portes V3.7

## Configuration nécessaire dans le vrai dépôt

- `RAILWAY_TOKEN` et `RAILWAY_PROJECT_ID` pour les déploiements ;
- `APP_PUBLIC_URL` pour les preuves post-déploiement ;
- `APP_PASSWORD` pour le test Chromium authentifié ;
- `THE_ODDS_API_KEY` et `DATABASE_URL` pour le benchmark historique ;
- `DATABASE_URL` et `BACKUP_ENCRYPTION_PASSPHRASE` pour la sauvegarde cloud chiffrée.

## Portes opérationnelles

- ne pas considérer un déploiement réussi si `/api/release` diverge ;
- garder `verify_browser=true` pour les déploiements normaux ; l’absence de `APP_PASSWORD` doit alors bloquer le run ;
- ne pas lancer `execute_sample` sans avoir lu le plan `plan_only` ;
- ne jamais dépasser 30 événements, 31 appels de découverte ou 200 crédits dans le workflow de validation ;
- ne lancer un rollback qu’avec le SHA d’un commit dont les artefacts ont déjà été exploités ou examinés ;
- ne pas considérer une sauvegarde valide si la restauration temporaire échoue ;
- conserver la phrase de chiffrement hors du dépôt et hors des conversations.

## Dette technique connue

- cinq `ResourceWarning` SQLite subsistent dans les tests historiques ;
- le benchmark court s’exécute sur un runner GitHub, tandis que `historical-worker` reste réservé aux travaux futurs plus longs ;
- le smoke test contre Railway doit encore être exécuté après l’intégration réelle ;
- la sauvegarde est logique et portable, pas une sauvegarde physique PostgreSQL point-in-time.

## Portes statistiques

- aucun avantage rentable démontré ;
- aucune promotion automatique ;
- 1 000 observations historiques et 200 résultats live restent les seuils de première revue sérieuse ;
- zéro violation temporelle acceptée ;
- stabilité par fold, calibration et CLV restent obligatoires.
