# Upgrade V4.2.1 → V4.3.0

## Changements

- produit quotidien sans cotes ;
- calendrier gratuit composite et mis en cache ;
- horizon par défaut de 31 jours ;
- prédictions modèle seules persistées de manière idempotente ;
- diagnostic du modèle ;
- pare-feu de crédits ;
- cold-start explicite pour les clubs sans historique ;
- workflow `Refresh daily product` ;
- cron quotidien modèle seul ;
- cotes et evidence payants désactivés par défaut.

## Variables recommandées

```text
DAILY_FIXTURE_HORIZON_DAYS=31
DAILY_ODDS_ENABLED=false
DAILY_ODDS_MAX_CREDITS=0
HISTORICAL_EVIDENCE_ENABLED=false
SHADOW_MODE_ENABLED=false
```

## Procédure

1. appliquer le patch ou remplacer le dépôt ;
2. commit et push ;
3. lancer `Deploy production` avec vérification navigateur ;
4. vérifier la version `4.3.0` ;
5. lancer `Refresh daily product` avec un horizon de 31 jours ;
6. contrôler le dashboard, les diagnostics et le pare-feu ;
7. ne réactiver aucune dépense fournisseur.
