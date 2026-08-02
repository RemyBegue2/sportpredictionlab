# Sports Prediction Lab V3.1 Cloud

Application privée de recherche pour prédictions pré-match football/tennis, comparaison Winamax, consensus de marché, historique des cotes et journalisation PostgreSQL.

La V3.1 transforme la V3 locale en service utilisable depuis une URL. Elle n'ajoute pas de nouvelle revendication de performance du modèle.

## Ce que livre la V3.1

- déploiement Docker sur Railway ou Render ;
- interface web mobile et ordinateur ;
- accès privé par mot de passe ;
- session signée, cookie `SameSite=Strict` et protection CSRF ;
- clé The Odds API uniquement côté serveur ;
- PostgreSQL pour les événements, snapshots, prédictions et synchronisations ;
- tâche planifiée pour récupérer les cotes ;
- page « Paris du jour » alimentée par les prédictions persistées ;
- expiration automatique des cotes anciennes à l'affichage ;
- endpoints distincts de liveness et readiness ;
- journal des dernières prédictions dans l'interface ;
- aucune connexion au compte Winamax et aucun placement automatique.

## Architecture

```text
Navigateur
   │ HTTPS + session privée
   ▼
FastAPI + interface statique
   ├── modèles football et tennis
   ├── comparaison Winamax / consensus
   ├── contrôle de fraîcheur
   └── journal d'audit
          │
          ▼
      PostgreSQL
          ▲
          │
Cron de synchronisation ── The Odds API
```

## Déploiement recommandé : Railway

1. Publier ce dossier dans un dépôt GitHub privé.
2. Créer un projet Railway à partir du dépôt.
3. Ajouter un service PostgreSQL.
4. Configurer les variables suivantes sur le service web :

```text
APP_ENV=production
APP_AUTH_REQUIRED=true
APP_COOKIE_SECURE=true
APP_PASSWORD=<mot de passe long>
APP_SESSION_SECRET=<secret aléatoire de 32 caractères minimum>
THE_ODDS_API_KEY=<votre clé>
DATABASE_URL=${{Postgres.DATABASE_URL}}
ODDS_SYNC_SPORTS=soccer_epl
ODDS_STALE_MINUTES=15
```

5. Générer un domaine public Railway.
6. Dupliquer le service depuis le même dépôt pour le cron.
7. Dans le service cron, sélectionner `railway.cron.toml` comme fichier de configuration et réutiliser `DATABASE_URL` et `THE_ODDS_API_KEY`.

Le fichier `railway.toml` configure le Dockerfile, la migration, le démarrage, le healthcheck et la politique de redémarrage. Voir `DEPLOY_RAILWAY.md`.

## Déploiement alternatif : Render Blueprint

Le fichier `render.yaml` crée :

- un service web Docker ;
- une base PostgreSQL ;
- un cron toutes les quinze minutes.

Render demande `APP_PASSWORD` et `THE_ODDS_API_KEY` lors de la création. Le secret de session est généré automatiquement. Le Blueprint utilise des ressources payantes `starter` et une base `basic-256mb`; vérifiez les tarifs affichés avant confirmation.

Voir `DEPLOY_RENDER.md`.

## Pourquoi pas Netlify seul ?

Le projet nécessite un runtime Python persistant, CatBoost, PostgreSQL et une tâche planifiée. Netlify peut servir une façade statique, mais ne remplace pas proprement le backend FastAPI. Ajouter Netlify devant Railway/Render créerait deux déploiements et une configuration CORS sans bénéfice suffisant pour cette version.

## Générer les secrets

```bash
python scripts/generate_cloud_secrets.py
```

Copiez les deux valeurs dans le gestionnaire de secrets de la plateforme. Ne créez pas de fichier `.env` dans le dépôt.

## Utilisation locale facultative

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
python scripts/train_snapshot.py
uvicorn webapp:app --reload
```

Le mode local utilise SQLite dans `/tmp` et désactive l'authentification par défaut.

Pour reproduire le mode cloud avec Docker Compose :

```bash
export POSTGRES_PASSWORD='un-secret-base-long'
export APP_PASSWORD='un-mot-de-passe-long'
export APP_SESSION_SECRET='une-valeur-aleatoire-d-au-moins-32-caracteres'
export THE_ODDS_API_KEY='votre-cle'
docker compose up --build
```

## Synchronisation des cotes

Le cron par défaut collecte uniquement l'EPL pour protéger le quota :

```bash
python scripts/sync_current_odds.py --football soccer_epl
```

Le tennis est volontairement désactivé par défaut :

```bash
python scripts/sync_current_odds.py \
  --football soccer_epl \
  --include-tennis \
  --max-tennis-tournaments 4
```

Chaque exécution :

1. demande les cotes au fournisseur ;
2. normalise et dévigue les marchés ;
3. persiste les snapshots sans doublons ;
4. bloque les événements déjà commencés ;
5. calcule les prédictions couvertes ;
6. journalise les analyses ;
7. renvoie un résumé sans secret.

## Paris du jour

`GET /api/bets/today` utilise d'abord PostgreSQL. Les prédictions sont dédupliquées par événement. Une cote trop ancienne est reclassée `à actualiser`, même si son verdict initial était positif.

Une shortlist vide est un résultat valide.

## Endpoints cloud

Publics :

- `GET /api/health` : liveness minimal pour la plateforme ;
- `GET /login` et `POST /api/auth/login`.

Protégés lorsque `APP_AUTH_REQUIRED=true` :

- `GET /api/ready` : modèles, intégrité, base et configuration ;

- `GET /api/catalog`
- `GET /api/metrics`
- `GET /api/bets/today`
- `GET /api/odds/status`
- `GET /api/odds/football/slate`
- `GET /api/odds/tennis/slate`
- `GET /api/history/predictions`
- `GET /api/history/sync-runs`
- `POST /api/football/predict`
- `POST /api/tennis/predict`

Les requêtes d'écriture authentifiées exigent `X-CSRF-Token`.

## Vérifier un déploiement

```bash
APP_PASSWORD='votre-mot-de-passe' \
python scripts/cloud_smoke_test.py https://votre-domaine.example
```

Le script vérifie la santé, la connexion, la readiness, le catalogue et le journal, puis se déconnecte.

## Tests

```bash
pytest -q
coverage run -m pytest -q
coverage report -m
```

État livré : **41 tests réussis**. La base, la déduplication, l'authentification, le CSRF, les configurations cloud, la fraîcheur du slate et les endpoints sont testés avec SQLite et des fournisseurs simulés.

## Limites importantes

- Aucun appel réel à votre clé n'a été effectué pendant la génération.
- PostgreSQL managé et le cron n'ont pas pu être exécutés dans cet environnement.
- Le Dockerfile a été inspecté, mais aucun moteur Docker n'était disponible pour construire l'image ici.
- `create_all` initialise le schéma, mais une future évolution de colonnes nécessitera Alembic ou une migration versionnée.
- Le limiteur de connexion est en mémoire et convient à une seule instance ; plusieurs réplicas nécessiteraient Redis.
- Le snapshot football reste petit et limité à l'EPL.
- Le tennis embarqué reste Elo non calibré et doit s'abstenir.
- La performance contre Winamax et la closing line n'est pas encore démontrée.

## Documents

- `AUDIT_MULTI_ROLES_V3_1.md` : audit contradictoire et arbitrages.
- `RESULTATS_V3_1.md` : validations réellement exécutées.
- `DEPLOY_RAILWAY.md` : procédure Railway.
- `DEPLOY_RENDER.md` : procédure Render.
- `CLOUD_ARCHITECTURE.md` : architecture et modèle de données.
- `SECURITY.md` : menace, secrets et limites.
- `MODEL_CARD.md` : portée statistique du service.
- `ROADMAP_V3.md` : benchmark historique et prochaines étapes.
