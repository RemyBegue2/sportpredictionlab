# Mise à niveau V3.7.3 → V3.8 sans Python local

## Important

L'archive d'upgrade ne contient pas les modèles ni les données actives. Elle ne doit pas remplacer :

```text
artifacts/football_model.joblib
artifacts/tennis_model.joblib
artifacts/metrics.json
artifacts/artifact_manifest.json
artifacts/fresh_rebuild_report.json
data/real/
```

## Installation depuis le navigateur

1. Décompresser `sports_prediction_v3_8_upgrade.zip`.
2. Copier son contenu à la racine du dépôt GitHub.
3. Accepter le remplacement des fichiers existants.
4. Vérifier que ces chemins existent :

```text
.github/workflows/estimate-historical-sample.yml
.github/workflows/run-historical-sample.yml
sports_predictor/evidence_quality.py
sports_predictor/sample_plan.py
scripts/estimate_historical_sample.py
scripts/build_evidence_report.py
```

5. Créer le commit :

```text
Upgrade to V3.8 cloud evidence run
```

## Variables Railway

Sur `sportpredictionlab` et `shadow-cron` :

```text
MODEL_VERSION=3.8.0
```

## Déploiement

Dans GitHub :

```text
Actions
→ Deploy production
→ Run workflow
```

Laisser les trois options activées.

## Première utilisation V3.8

### Étape 1 — estimation gratuite

```text
Actions
→ Estimate historical sample
→ Run workflow
```

Paramètres prudents :

```text
sample_events = 30
max_discovery_calls = 14
max_odds_credits = 120
```

Le résumé doit indiquer :

```text
Provider API calls executed: 0
Plan request ID: REQ-...
```

### Étape 2 — exécution approuvée

Ouvrir :

```text
Actions
→ Run historical sample
→ Run workflow
```

Recopier exactement :

- le `REQ-...` ;
- les mêmes dates ;
- les mêmes plafonds ;
- `EXECUTE_APPROVED_SAMPLE` dans confirmation.

Le workflow publie le rapport, redéploie l'interface puis devient rouge si la porte qualité est bloquée. Ce rouge est alors un diagnostic métier, pas forcément une panne du code.
