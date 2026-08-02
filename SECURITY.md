# Sécurité V3.5

## Surfaces publiques

- `/api/health` : liveness minimale ;
- `/api/release` : version, commit, hashes et intégrité, sans secret.

Toutes les autres pages et API opérationnelles restent protégées lorsque `APP_AUTH_REQUIRED=true`.

## Secrets

Les valeurs suivantes restent exclusivement dans Railway/GitHub Secrets :

- `THE_ODDS_API_KEY` ;
- `APP_PASSWORD` ;
- `APP_SESSION_SECRET` ;
- `DATABASE_URL` ;
- `RAILWAY_TOKEN`.

Le manifeste et le handoff utilisent une liste blanche. Ils n’énumèrent pas les variables d’environnement.

## Écritures sensibles

La transition de statut des modèles :

- nécessite une session authentifiée ;
- est protégée par CSRF ;
- valide les transitions autorisées ;
- exige un motif ;
- conserve un journal.

## Artefacts

Joblib/Pickle reste dangereux si un attaquant peut remplacer à la fois les artefacts et leurs manifestes. Les hashes améliorent la traçabilité mais ne remplacent pas une signature cryptographique et une chaîne de distribution fiable.

## Backup

Le backup portable ne contient pas l’URL de base. Le fichier peut toutefois contenir des données d’audit et doit être stocké comme donnée privée. Les sauvegardes managées Railway restent nécessaires.
