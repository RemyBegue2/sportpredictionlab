# Changelog

## 3.1.1 — Correctif déploiement Railway

- correction des imports des scripts `db_migrate.py` et `sync_current_odds.py` ;
- exécution Railway/Render via `python -m` pour garantir la présence de la racine du projet dans `sys.path` ;
- ajout de tests de régression pour les entrypoints de migration et de cron.

## 2.2.0

- Ajout de la section « Paris du jour ».
- Ajout de la saisie manuelle des cotes Winamax 1N2 et vainqueur tennis.
- Marchés dévigés, fair odds, edge, EV brute et EV robuste.
- Haircut d'incertitude et abstention sur modèle non calibré.
- Refus des cotes partielles ; cote non horodatée classée « à actualiser ».
- Aucun stake sizing, aucun login bookmaker et aucune exécution automatique.
- Endpoint `GET /api/bets/today` et slate audité du 2 août 2026.
- Suite portée à 24 tests ; couverture globale maintenue à 88 %.

## 2.1.0

- Correction de la fuite temporelle entre événements de même timestamp.
- Splits et backtests groupés par date/tournoi.
- Tennis snapshot passé en Elo-only non calibré.
- Filtrage walkover/default/retirement par défaut.
- Rangs du match acceptés par le backtest tennis.
- Rejet des rétro-prédictions.
- Manifeste SHA-256 des artefacts.
- En-têtes HTTP de sécurité et Docker non-root/read-only.
- Validation des codes de ligue, tailles de téléchargement et écritures atomiques.
- Correction du tableau de scores dans le site.

## 3.1.0 — Cloud privé

- ajout PostgreSQL/SQLite via SQLAlchemy ;
- ajout authentification, session et CSRF ;
- ajout liveness/readiness ;
- ajout journal des prédictions et synchronisations ;
- ajout slate quotidien depuis PostgreSQL avec expiration des cotes ;
- ajout Railway web/cron et Render Blueprint ;
- ajout scripts migration, synchronisation, secrets et smoke test ;
- interface cloud et historique ;
- suite portée à 41 tests ;
- persistance corrigée pour conserver l’analyse de marché des slates fournisseur ;
- `/api/ready` protégé en mode authentifié ;
- reclassification des anciennes cotes vérifiée depuis la chaîne slate → base → Paris du jour.
