# Runbook V3.9 — navigateur uniquement

## Déployer

```text
GitHub → Actions → Deploy production → Run workflow
```

Version attendue : `3.9.0`.

## Recalculer le dernier lot sans crédit

```text
GitHub → Actions → Recompute latest evidence → Run workflow
```

Configuration requise :

```text
RAILWAY_TOKEN
RAILWAY_PROJECT_ID
APP_PUBLIC_URL
```

Non requis :

```text
THE_ODDS_API_KEY
DATABASE_URL
```

## Vérifier

```text
/api/health
/api/release
/api/evidence
```

Le rapport doit afficher un funnel et une matrice bookmaker. Une ancienne métrique V3.8 doit être remplacée par `Recalcul requis` tant que le workflow n’a pas terminé.

## Générer le pack de reprise

```text
GitHub → Actions → Generate handoff package → Run workflow
```

Télécharger l’artefact `sports-prediction-handoff-v3.9`.

## Ne pas faire

- ne pas relancer un lot payant pour corriger un problème de dénominateur ;
- ne pas modifier le modèle sur un petit lot ;
- ne pas coller de secret dans le dépôt ou une conversation ;
- ne pas utiliser « Re-run jobs » après un changement de workflow : lancer un nouveau run.
