# Déploiement Railway V3.2

## Services

1. **Web** — `railway.toml`
2. **PostgreSQL** — plugin Railway
3. **Cron courant** — `railway.cron.toml`
4. **Worker historique manuel** — `railway.worker.toml`

## Web

Conserver les variables de la V3.1.2 et ajouter :

```text
MODEL_VERSION=3.2.0
```

Le pre-deploy reste :

```text
python -m scripts.db_migrate
```

Il crée les nouvelles tables avec SQLAlchemy. Cette méthode ne remplace pas Alembic pour de futures migrations destructives ou modifications de colonnes.

## Cron courant

Créer un second service depuis le même dépôt et sélectionner `railway.cron.toml` comme chemin de configuration. Il synchronise les cotes puis les scores récents toutes les quinze minutes.

Variables :

```text
APP_ENV=production
APP_AUTH_REQUIRED=false
DATABASE_URL=${{Postgres.DATABASE_URL}}
THE_ODDS_API_KEY=<secret>
ODDS_SYNC_SPORTS=soccer_epl
```

## Worker historique

Créer un troisième service depuis le même dépôt et sélectionner `railway.worker.toml`.

Variables obligatoires :

```text
APP_ENV=production
APP_AUTH_REQUIRED=false
DATABASE_URL=${{Postgres.DATABASE_URL}}
THE_ODDS_API_KEY=<secret>
BACKFILL_PLAN_DIR=data/odds_api/backfill
BACKFILL_MAX_CREDITS=5000
```

Le plan doit être présent dans l’image ou téléchargé vers un stockage accessible. Ne démarrez pas le worker avec `BACKFILL_MAX_CREDITS=0`.

Le worker est volontairement `NEVER` pour sa politique de redémarrage. Une erreur de budget ou de données nécessite une inspection humaine.

## Après déploiement

Vérifier :

```text
/api/health
/api/ready
/api/odds/status
/api/benchmark/summary
/api/admin/backfills
/api/admin/data-quality
```

Puis vérifier que la première exécution cron ajoute des lignes à `sync_runs` et que la page reste accessible après un redémarrage du service web.
