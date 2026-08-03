# Résultats vérifiés — V4.1.1

Date de validation : 3 août 2026.

## Incident corrigé

- Railway utilisait `/api/ready` comme healthcheck alors que la route était protégée par l’authentification : une sonde sans session recevait `401`.
- Le workflow de sauvegarde recevait une URL PostgreSQL avec un port vide. SQLAlchemy échouait avant la connexion avec `ValueError: invalid literal for int()`.

## Correctifs validés

- `/api/ready` est public, tandis que les routes métier restent protégées.
- Le workflow de backup préfère `DATABASE_PUBLIC_URL` et garde `DATABASE_URL` seulement comme repli.
- Les URL entourées de guillemets sont normalisées.
- Les ports vides/non numériques et les hôtes Railway privés depuis GitHub sont refusés proprement.
- Aucun identifiant de base n’est réaffiché dans l’erreur de validation.
- Un backup et une restauration portables SQLite ont été exécutés avec succès.

## Validation

- 161 tests réussis par quatre lots : 37 + 41 + 58 + 25 ;
- aucun échec ;
- compilation Python réussie ;
- syntaxe JavaScript réussie ;
- 12 fichiers YAML parsés ;
- 6 tests dédiés au hotfix réussis.

## Non vérifié ici

- connexion réelle au PostgreSQL Railway ;
- exécution du workflow dans le dépôt GitHub de l’utilisateur ;
- nouveau déploiement Railway.

Le secret GitHub `DATABASE_PUBLIC_URL` doit encore être configuré avec l’URL publique résolue et son port numérique.
