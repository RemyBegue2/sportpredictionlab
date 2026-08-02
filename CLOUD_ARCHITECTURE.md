# Architecture cloud V3.1

## Composants

### Service web

FastAPI sert l'interface, les modèles et les endpoints. Les artefacts sont vérifiés par manifeste avant chargement.

### Base PostgreSQL

Tables :

- `events` : identité fournisseur et heure de début ;
- `odds_snapshots` : bookmaker, marché, sélection, cote et horodatages ;
- `predictions` : fixture, probabilités, analyse de marché, décision et version ;
- `sync_runs` : statut du collecteur, volume inséré et quota.

Les snapshots disposent d'une contrainte d'unicité qui évite de compter plusieurs fois la même cote observée.

### Cron

Le cron exécute un processus court qui collecte, persiste, analyse et se termine. Les erreurs sont résumées sans inclure la clé ni l'URL de base de données.

## Flux d'une prédiction manuelle

1. Authentification par session.
2. Requête POST avec token CSRF.
3. Calcul du modèle.
4. Analyse de marché facultative.
5. Écriture de l'audit en base.
6. Réponse avec `prediction_id`.

L'étape 5 est obligatoire : une erreur de stockage transforme la réponse en 503.

## Flux d'une synchronisation

1. Requête serveur The Odds API.
2. Normalisation en lignes.
3. Écriture des événements et cotes.
4. Détection in-play.
5. Appariement d'identités.
6. Analyse modèle/marché.
7. Écriture des prédictions couvertes.
8. Journal du run et du quota.

## Scalabilité

La V3.1 cible une seule instance web. Pour plusieurs réplicas, il faudra :

- rate limiting partagé dans Redis ;
- verrou distribué pour les synchronisations ;
- migrations versionnées ;
- pool PostgreSQL géré ;
- métriques et tracing centralisés.
