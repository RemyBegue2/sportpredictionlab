# Déployer la V3.3 sur Railway

## 1. Mettre à jour le service web

Remplace le dépôt par le contenu de l’archive, puis :

```bash
git add -A
git commit -m "Upgrade to V3.3 shadow mode"
git push
```

Le service existant utilise `railway.toml`. Le pre-deploy créera les nouvelles tables sans supprimer les anciennes données.

Variables recommandées :

```text
APP_ENV=production
APP_AUTH_REQUIRED=true
APP_COOKIE_SECURE=true
APP_PASSWORD=...
APP_SESSION_SECRET=...
DATABASE_URL=${{Postgres.DATABASE_URL}}
THE_ODDS_API_KEY=...
MODEL_VERSION=3.3.0
ODDS_SYNC_SPORTS=soccer_epl
ODDS_STALE_MINUTES=15
SHADOW_MODE_ENABLED=true
SHADOW_QUOTA_FLOOR=100
MODEL_MAX_AGE_DAYS=365
```

## 2. Créer le service cron

1. Nouveau service depuis le même dépôt.
2. Nom : `shadow-cron`.
3. Settings → Config file path : `/railway.cron.toml`.
4. Référence la même base PostgreSQL.
5. Ajoute la clé The Odds API et les variables shadow.
6. Ne génère pas de domaine public.

Commande exécutée :

```text
python -m scripts.run_shadow_cycle
```

Planning : toutes les quinze minutes.

## 3. Contrôler le premier cycle

Dans les logs du service cron, attends un JSON contenant :

```json
{
  "status": "ok",
  "events_seen": 0,
  "predictions_created": 0,
  "predictions_reused": 0,
  "predictions_settled": 0,
  "quota_remaining": 0
}
```

Les zéros sont possibles hors saison ou sans événement. Le champ important est l’absence d’erreur de configuration.

## 4. Tester dans l’application

- `/api/health` : version 3.3.0 ;
- `/api/ready` : base et artefacts disponibles ;
- `/api/shadow/summary` : dernier cycle visible ;
- section Shadow : modèle football marqué `degraded` tant qu’il n’est pas réentraîné.

## 5. Sauvegardes

Active une sauvegarde PostgreSQL et teste une restauration avant de compter sur le journal comme historique durable.
