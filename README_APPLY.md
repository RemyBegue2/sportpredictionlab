# Application de la V4.5.0

Depuis un dépôt V4.4.0 propre :

```bash
git apply sportpredictionlab-v4.5.0.patch
git add .
git commit -m "Add automated shadow learning and simple UI"
git push
```

Déployer ensuite avec **Deploy production** et conserver `verify_browser=true`.

Au premier déploiement, garder fermés :

```text
DAILY_ODDS_ENABLED=false
DAILY_ODDS_MAX_CREDITS=0
SHADOW_MODE_ENABLED=false
AUTOMATED_SHADOW_ENABLED=false
HISTORICAL_EVIDENCE_ENABLED=false
```

Aucun modèle ni fichier de données ne doit être supprimé lors de l’application du patch.
