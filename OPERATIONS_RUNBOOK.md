# Runbook V3.6

## Après chaque déploiement

1. `/api/health` doit afficher `3.6.0`.
2. `/api/release` doit confirmer le commit et l’intégrité.
3. `/api/model-decision` doit contenir `automatic_promotion: false` et `profitability_claim: false`.
4. Recharger l’interface et vérifier la section « Décision modèle ».

## Backfill de validation

- Limite par défaut : 30 événements.
- Toujours faire un dry-run.
- Ne jamais augmenter le plafond après le lancement d’un même plan.
- Archiver `plan.json`, `requests.csv`, `targets.csv` et `state.json`.

## Backfill complet

- Examiner le coût réel du lot de validation.
- Générer un nouveau plan avec `--full`.
- Copier exactement son `plan_id` dans `BACKFILL_APPROVE_PLAN`.
- Le worker Railway doit rester en redémarrage `NEVER`.

## Incident

- Ne pas supprimer `state.json` pour contourner une erreur.
- Consulter `data_quality_issues` et les logs du worker.
- Reprendre seulement après correction de la cause.
