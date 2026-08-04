# Upgrade V4.5.0 → V4.6.0

## Changements

- cockpit simple à trois onglets, un seul panneau visible ;
- calibration séparée football/tennis ;
- holdout chronologique et veto de non-dégradation ;
- registre d’expériences stable ;
- audit de lineage temporelle des features ;
- endpoint et workflow Feature Lab à zéro crédit ;
- version frontend `app.js?v=4.6.0`.

## Application

```bash
git apply sportpredictionlab-v4.6.0.patch
git add .
git commit -m "Add calibration feature lab and compact cockpit"
git push
```

Déployer avec `verify_browser=true`, puis vérifier `/api/feature-lab`.

## Compatibilité

Aucune migration de schéma n’est nécessaire. Le laboratoire réutilise les observations shadow et le registre de benchmark existants. Les limites et plafonds V4.5 restent inchangés.
