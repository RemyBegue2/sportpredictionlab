# Runbook opérationnel — V4.4.0

## Déploiement

1. Déployer web et cron avec `Deploy production`.
2. Garder `verify_browser=true`.
3. Vérifier `/api/ready` et `/api/release` : version `4.4.0`.
4. Vérifier le produit quotidien à zéro crédit.

## Activation limitée du marché

Dans Railway :

```text
DAILY_ODDS_ENABLED=true
DAILY_ODDS_MAX_CREDITS=3
SHADOW_MODE_ENABLED=true
DAILY_TENNIS_MAX_TOURNAMENTS=2
HISTORICAL_EVIDENCE_ENABLED=false
```

Lancer manuellement `Capture daily football and tennis research` avec :

```text
max_credits: 3
tennis_limit: 2
confirmation: CAPTURE_DAILY_MARKET
```

Contrôler que `credits_consumed <= 3`. Une absence de signal est valide.

## Règlement

Après la fin des matchs, lancer `Settle daily football and tennis research` :

```text
max_credits: 3
confirmation: SETTLE_DAILY_MARKET
```

Contrôler les résultats importés, les événements réglés et le plafond.

## Optimisation

Lancer `Optimise simulated ROI policy`. Ce workflow doit consommer zéro crédit.

États attendus :

- moins de 30 événements : `not_evaluable` ;
- 30 à 59 : politique candidate possible, méta-modèle non évaluable ;
- 60 ou plus : méta-modèle potentiellement candidat après holdout.

## Interface

Le panneau `ROI simulé` doit afficher :

- matchs football et tennis du dernier run ;
- signaux expérimentaux ;
- crédits consommés ;
- bankrolls simulées ;
- politique et holdout ;
- état du méta-modèle.

## Après la capture

Refermer le pare-feu lorsque les captures ne sont pas nécessaires :

```text
DAILY_ODDS_ENABLED=false
DAILY_ODDS_MAX_CREDITS=0
SHADOW_MODE_ENABLED=false
```

Le produit quotidien modèle seul continue de fonctionner.
