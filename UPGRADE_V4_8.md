# Upgrade V4.7.0 → V4.8.0

## Changements

- pipeline Evidence Acceleration à zéro crédit ;
- import tennis normalisé et mis en quarantaine ;
- catalogue de datasets et générations de holdout ;
- diagnostic du hold football par sous-groupes ;
- test public longue session mesurant DOM et réseau ;
- Alembic pour les nouvelles tables ;
- actions GitHub figées par SHA complet ;
- carte d’action dans Aujourd’hui ;
- aucun nouvel onglet simple.

## Application

```bash
git apply sportpredictionlab-v4.8.0.patch
git add .
git commit -m "Add evidence acceleration and production hardening"
git push
```

## Migration

Railway et Render exécutent déjà :

```bash
python -m scripts.db_migrate
```

Pour une base pré-V4.8, le script adopte la baseline puis applique la migration des tables `dataset_catalog` et `holdout_generations`.

## Vérifications

```text
/api/release                 4.8.0
/api/ready                   ready
/api/evidence-acceleration   réponse JSON
```

Puis lancer :

```text
Run evidence acceleration
Verify public long session
```

## Compatibilité

- le champion actuel reste intact ;
- les observations historiques restent lisibles ;
- les anciennes lignes sans timestamps sont marquées `legacy_unverified` ;
- aucun workflow d’entraînement ne consomme de crédit fournisseur ;
- les captures live restent désactivées par défaut.
