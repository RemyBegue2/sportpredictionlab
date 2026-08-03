# V3.8.6 — Flat file-only historical planner hotfix

## Cause corrigée

L'archive V3.8.5 contenait un dossier enveloppe `sports_prediction_v3_8_5_cumulative_hotfix/`.
Si ce dossier était copié dans le dépôt, les vrais fichiers racine n'étaient pas remplacés.
Le workflow continuait alors d'exécuter l'ancien planner qui appelait `init_database`.

## Garanties V3.8.6

- Cette archive est plate : `.github/`, `scripts/`, `sports_predictor/` et `tests/` sont directement à sa racine.
- `scripts/plan_historical_backfill.py` n'importe plus SQLAlchemy, `CloudSettings`, `init_database` ou `create_backfill_job`.
- L'ancien argument `--register-job` est accepté mais ignoré, donc même un ancien appel ne peut plus ouvrir PostgreSQL.
- Le workflow vérifie le marqueur V3.8.6 avant la planification et explique clairement si le mauvais fichier est encore présent.
- Le workflow historique reste en stockage fichiers et n'utilise pas `DATABASE_URL`.

## Vérification dans GitHub

Ouvrir `scripts/plan_historical_backfill.py` puis rechercher `init_database`.
Résultat attendu : aucune occurrence.
Rechercher ensuite `"version": "3.8.6"`.
Résultat attendu : une occurrence.

Créer un nouveau commit puis lancer une nouvelle exécution de `Run historical sample`.
Ne pas relancer une ancienne exécution.
