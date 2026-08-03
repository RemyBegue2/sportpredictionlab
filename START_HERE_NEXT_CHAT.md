# Sports Prediction Lab — point de reprise V4.3.0

## État préparé

- Version : **4.3.0 — Daily Product Recovery & Credit Firewall**.
- Exploitation : GitHub Actions + Railway, sans Python local.
- Produit principal : calendrier et probabilités Premier League sans cotes payantes.
- Modèle football chargé : `3.4.0-fresh`, statut de recherche opérationnel, pas validé pour une shortlist marché.
- Cotes quotidiennes : désactivées par défaut.
- Evidence historique payante : suspendue par défaut.

## Première action

1. Déployer V4.3.0.
2. Vérifier `/api/ready`, `/api/release`, `/api/model-diagnostics` et `/api/credit-firewall`.
3. Lancer **Refresh daily product**.
4. Confirmer `credits_consumed=0`.
5. Vérifier les matchs, probabilités et raisons d’absence de shortlist dans l’interface.

## Variables recommandées

```text
DAILY_ODDS_ENABLED=false
DAILY_ODDS_MAX_CREDITS=0
HISTORICAL_EVIDENCE_ENABLED=false
SHADOW_MODE_ENABLED=false
DAILY_FIXTURE_HORIZON_DAYS=31
DAILY_FIXTURE_CACHE_HOURS=6
```

## Règles

- ne pas relancer de préflight ou backfill payant sans justification et approbation humaine ;
- ne pas interpréter une probabilité modèle comme un pari ;
- ne pas forcer une shortlist lorsqu’aucun avantage live n’est validé ;
- aucune mise, connexion bookmaker, promotion ou exécution automatique.
