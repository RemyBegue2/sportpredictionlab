# Hotfix Railway V3.1.1

## Symptôme

Railway termine la phase **Build**, puis échoue pendant **Deploy > Pre-deploy command**.

## Cause racine

La commande V3.1.0 était :

```bash
python scripts/db_migrate.py
```

Exécuté comme fichier, Python place `scripts/` en tête du chemin d'import. La racine du dépôt n'était pas ajoutée par `db_migrate.py`, ce qui provoquait :

```text
ModuleNotFoundError: No module named 'sports_predictor.cloud_config'
```

Le script de cron `sync_current_odds.py` avait le même défaut latent.

## Correction

Les entrypoints cloud utilisent maintenant :

```bash
python -m scripts.db_migrate
python -m scripts.sync_current_odds --football soccer_epl
```

Les deux scripts ajoutent également explicitement la racine du projet à `sys.path`, afin que l'exécution directe reste compatible.

La migration échoue désormais avec un message explicite lorsque Railway/Render ne possède pas de `DATABASE_URL` PostgreSQL ou lorsque les secrets d'authentification obligatoires sont absents.

## Variables Railway requises

```text
APP_ENV=production
APP_AUTH_REQUIRED=true
APP_COOKIE_SECURE=true
APP_PASSWORD=<12 caractères minimum>
APP_SESSION_SECRET=<32 caractères minimum>
DATABASE_URL=${{Postgres.DATABASE_URL}}
THE_ODDS_API_KEY=<clé The Odds API>
ODDS_SYNC_SPORTS=soccer_epl
ODDS_STALE_MINUTES=15
```

Ajoutez d'abord un service PostgreSQL au projet Railway. Le nom utilisé dans la référence doit correspondre exactement au nom du service, généralement `Postgres`.

## Validation

- 45 tests réussis ;
- exécution directe de la migration validée ;
- exécution de la migration comme module validée ;
- import du cron en exécution directe et comme module validé ;
- TOML Railway et YAML Render parsables ;
- compilation Python validée.
