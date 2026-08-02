# Runbook opérationnel V3.5

## Vérifier le déploiement

```text
GET https://VOTRE-DOMAINE/api/health
GET https://VOTRE-DOMAINE/api/release
```

Contrôler :

- `version = 3.5.0` ;
- `source_commit` correspond au commit Railway ;
- `artifact_integrity_ok = true` ;
- `football_model_sha256` correspond au manifeste attendu.

## Générer la preuve locale

```bash
python -m scripts.generate_release_manifest
python -m scripts.export_handoff
```

## Incident : workflow vert mais ancienne interface

1. Lire `/api/release`.
2. Comparer `source_commit` au dernier commit GitHub.
3. Si différent, Railway n’a pas déployé le bon commit.
4. Utiliser `Deploy Latest Commit`, jamais `Redeploy` sur une ancienne image.
5. Refaire la vérification avant de vider le cache navigateur.

## Incident : modèle inattendu

1. Lire `/api/system/status`.
2. Vérifier `football_model.artifact_sha256`.
3. Vérifier le registre des modèles.
4. Ne pas modifier le statut pour « réparer » un hash incohérent.
5. Restaurer un snapshot seulement après dry-run.

## Snapshot et rollback

```bash
python -m scripts.snapshot_release --release-id known-good
python -m scripts.rollback_release --release-id known-good
python -m scripts.rollback_release --release-id known-good --execute
```

## Backup applicatif

```bash
python -m scripts.portable_db_backup --backup
```

Tester la restauration sur une base vide séparée. Ne jamais tester directement sur la base de production.

## Rotation des secrets

Les secrets ne figurent pas dans le handoff. Une rotation se fait dans Railway/GitHub, jamais dans le dépôt ni dans la conversation.
