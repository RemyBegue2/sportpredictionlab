# Hotfix cumulatif V3.8.5 — échantillon historique sans dépendance PostgreSQL GitHub

## Cause corrigée

Le workflow `Run historical sample` initialisait PostgreSQL pendant la construction du plan et pendant la collecte. Une URL publique Railway mal copiée, notamment avec un port vide comme `host:/database`, faisait échouer SQLAlchemy avant même la collecte.

Cette dépendance n'est pas nécessaire pour un petit échantillon de validation. La V3.8.5 exécute donc ce workflow en mode fichiers isolés dans GitHub Actions.

## Changements

- `DATABASE_URL` n'est plus lu ni exigé par `run-historical-sample.yml`.
- `plan_historical_backfill` n'utilise plus `--register-job` dans ce workflow.
- `run_historical_backfill` reçoit `--storage files` et n'initialise pas SQLAlchemy.
- Les lignes de cotes, l'état, le plan et le rapport restent dans les fichiers du job et sont publiés comme artefact GitHub.
- Le benchmark n'utilise plus `--persist`, donc il ne tente pas non plus une connexion PostgreSQL.
- La sauvegarde PostgreSQL et les services Railway continuent d'utiliser leur propre `DATABASE_URL`; ils ne sont pas modifiés.

## Installation

Copier tout le contenu de l'archive à la racine du dépôt, accepter les remplacements, puis créer un nouveau commit :

`Fix historical sample database dependency v3.8.5`

Lancer ensuite une nouvelle exécution :

`Actions → Run historical sample → Run workflow`

Ne pas relancer une ancienne exécution.

## Configuration requise par ce workflow

- secret `THE_ODDS_API_KEY`
- secret `RAILWAY_TOKEN`
- secret `RAILWAY_PROJECT_ID`
- variable `APP_PUBLIC_URL`

`DATABASE_URL` n'est pas requis pour ce workflow. Il peut rester présent dans GitHub pour le workflow de sauvegarde.

## Validation

- 130 tests réussis.
- YAML des workflows valide.
- compilation Python valide.
- syntaxe JavaScript valide.
- reproduction exacte du défaut avec `DATABASE_URL=postgresql://user:password@example.com:/railway` : la construction du plan réussit désormais.
- test d'exécution file-only avec la même URL malformée : succès, sans initialisation SQLAlchemy.

## Limite assumée

Le petit échantillon est conservé dans les fichiers et artefacts du job GitHub. En cas d'interruption complète du runner, une nouvelle exécution recommence le petit lot. Ce choix supprime une dépendance réseau fragile et reste raisonnable pour un maximum de 30 événements.
