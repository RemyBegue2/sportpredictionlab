# Runbook cloud V3.8

## Déployer

```text
GitHub → Actions → Deploy production → Run workflow
```

## Vérifier sans redéployer

```text
GitHub → Actions → Verify production → Run workflow
```

## Estimer un lot historique sans crédit

```text
GitHub → Actions → Estimate historical sample → Run workflow
```

Télécharger l'artefact ou copier le `REQ-...` depuis le résumé.

## Exécuter le lot

```text
GitHub → Actions → Run historical sample → Run workflow
```

Conditions :

- mêmes paramètres que l'estimation ;
- `REQ-...` exact ;
- confirmation `EXECUTE_SAMPLE` ;
- clé The Odds API et base PostgreSQL configurées dans GitHub Secrets.

## Interpréter un workflow rouge

- erreur avant la collecte : problème de configuration ou de code ;
- rapport publié puis étape `Enforce quality gate` rouge : données insuffisantes ou invalides ;
- lire `artifacts/evidence_report_v3_8.json` dans l'artefact du workflow.

## Générer le pack de reprise

```text
GitHub → Actions → Generate handoff package → Run workflow
```

Télécharger `sports-prediction-handoff-v3.8` dans la section Artifacts.
