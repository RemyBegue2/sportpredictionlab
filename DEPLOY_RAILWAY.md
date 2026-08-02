# Déploiement Railway — V3.1

## 1. Préparer le dépôt

Publiez le dossier V3.1 dans un dépôt GitHub privé. Ne commitez jamais `.env`, la clé The Odds API ou les secrets générés.

## 2. Créer le service web

Dans Railway :

1. `New Project` → `Deploy from GitHub repo` ;
2. sélectionnez le dépôt ;
3. Railway détecte le `Dockerfile` et `railway.toml` ;
4. ajoutez un service PostgreSQL au projet ;
5. ajoutez les variables du README ;
6. référencez la base avec `DATABASE_URL=${{Postgres.DATABASE_URL}}` ;
7. générez un domaine pour le service web.

Le healthcheck public est `/api/health`. Après connexion, la page `/api/ready` doit retourner 200.

## 3. Créer le cron

Dupliquez le service depuis le même dépôt, puis :

1. choisissez `railway.cron.toml` comme fichier Config as Code ;
2. partagez `DATABASE_URL` et `THE_ODDS_API_KEY` ;
3. ne générez pas de domaine ;
4. vérifiez que la commande est `python -m scripts.sync_current_odds --football soccer_epl` ;
5. vérifiez le cron `*/15 * * * *`.

Le tennis n'est pas synchronisé par défaut pour éviter une consommation incontrôlée du quota.

## 4. Contrôles après déploiement

- `/api/health` retourne `ok` ;
- `/api/ready` retourne `ready` ;
- la page `/` redirige vers `/login` sans session ;
- la clé n'apparaît jamais dans l'inspecteur réseau ;
- `/api/odds/status` indique PostgreSQL connecté ;
- un run du cron ajoute des lignes dans `/api/history/sync-runs` ;
- les cotes trop anciennes passent à `à actualiser`.

## 5. Sauvegardes et coûts

Activez les sauvegardes disponibles sur le plan PostgreSQL choisi. Configurez une alerte de quota The Odds API et une alerte d'échec du cron. Les prix des plateformes évoluent : contrôlez le devis Railway avant validation.
