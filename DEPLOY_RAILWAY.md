# Déploiement Railway V3.7 depuis GitHub

## Configuration unique

Dans GitHub Actions, créer les secrets :

```text
RAILWAY_TOKEN
RAILWAY_PROJECT_ID
APP_PASSWORD
BACKUP_ENCRYPTION_PASSPHRASE
```

Créer les variables :

```text
APP_PUBLIC_URL=https://votre-domaine.up.railway.app
RAILWAY_ENVIRONMENT=production
RAILWAY_WEB_SERVICE=sportpredictionlab
RAILWAY_CRON_SERVICE=shadow-cron
```

`RAILWAY_TOKEN` est un Project Token Railway limité à l’environnement de production. Il autorise le workflow à envoyer le code aux services Railway.

## Déployer

```text
GitHub → Actions → Deploy production → Run workflow
```

Le workflow :

1. exécute tous les tests ;
2. génère la preuve du commit ;
3. déploie le web et le cron avec Railway CLI ;
4. attend que `/api/release` corresponde ;
5. ouvre l’interface dans Chromium et échoue sur une erreur JavaScript.

Aucun terminal et aucun Python local ne sont nécessaires.
