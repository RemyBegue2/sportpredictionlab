# Mise à niveau V3.4.4 → V3.5

## Objectif

Ajouter la preuve de déploiement, le registre des modèles/releases, le handoff et le rollback sans remplacer le modèle frais déjà produit dans votre dépôt.

## Procédure

1. Faire une copie ou un commit propre du dépôt actuel.
2. Décompresser `sports_prediction_v3_5_upgrade.zip` à la racine du dépôt.
3. Accepter le remplacement des fichiers de code.
4. Vérifier que les fichiers suivants sont toujours présents et n’ont pas été remplacés par le paquet :

```text
artifacts/football_model.joblib
artifacts/tennis_model.joblib
artifacts/metrics.json
artifacts/artifact_manifest.json
artifacts/fresh_rebuild_report.json
data/real/football_active.csv
```

5. Commit et push :

```bash
git add -A
git commit -m "Upgrade to V3.5 operational evidence"
git push
```

6. Mettre `MODEL_VERSION=3.5.0` sur le service web et `shadow-cron`.
7. Déployer le dernier commit.
8. Vérifier `/api/release`.

## Après déploiement

```text
version = 3.5.0
source_commit = dernier commit déployé
artifact_integrity_ok = true
```

Puis exécuter dans le dépôt :

```bash
python -m scripts.generate_release_manifest
python -m scripts.export_handoff
```

## Important

Le paquet d’upgrade omet volontairement les modèles et les données actives. Il ne peut donc pas restaurer un artefact frais supprimé avant l’extraction.
