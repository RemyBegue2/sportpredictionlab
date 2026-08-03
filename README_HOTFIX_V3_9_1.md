# Hotfix V3.9.1 — recompute réel

Le log `schema_version: 1.0` / `app_version: 3.8.0` prouve que le dépôt exécutait encore le générateur V3.8. Ce générateur renvoie le code de sortie 4 lorsque la porte qualité est bloquée, ce qui transforme un verdict métier normal en échec GitHub Actions.

Ce paquet remplace exactement :

- `.github/workflows/recompute-latest-evidence.yml`
- `scripts/build_evidence_report.py`
- `scripts/export_evidence_tables.py`
- `sports_predictor/evidence_quality.py`

Le workflow vérifie désormais les marqueurs V3.9 avant de commencer, puis contrôle que le rapport généré possède `schema_version=2.0`, un `funnel` et des `gates`. Une porte qualité bloquée reste un résultat publiable et ne fait plus échouer le job.
