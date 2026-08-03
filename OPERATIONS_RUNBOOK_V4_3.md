# Runbook opérationnel — V4.3.0

## Déploiement

1. Déployer le web et le cron avec `Deploy production`.
2. Garder `verify_browser=true`.
3. Vérifier `/api/ready` et `/api/release` : version attendue `4.3.0`.
4. Vérifier `/api/credit-firewall` : `daily_odds_enabled=false`, `daily_odds_max_credits=0`, `historical_evidence_enabled=false`.

## Premier rafraîchissement quotidien

Lancer `Refresh daily product` avec :

```text
date: vide
horizon_days: 31
```

Le workflow doit confirmer :

- zéro crédit consommé ;
- modèle non bloqué ;
- calendrier `available` ou `no_fixtures` ;
- probabilités persistées lorsqu’une rencontre est trouvée.

## Vérifications dans l’interface

- panneau quotidien chargé sans toast rouge ;
- matchs du jour ou prochains matchs visibles ;
- probabilités totalisant 100 % ;
- badge cold-start lorsque nécessaire ;
- raisons d’absence de shortlist affichées ;
- boutons de cotes payantes désactivés.

## En cas de calendrier indisponible

1. relancer une seule fois après 15 minutes ;
2. consulter `generation.error_type` sans chercher de secret dans les logs ;
3. vérifier l’accès sortant HTTPS de Railway ;
4. ne pas activer The Odds API pour compenser une panne de calendrier ;
5. conserver le pare-feu de crédits fermé.

## En cas d’absence de match aujourd’hui

Consulter `upcoming_events`. L’absence de rencontre le jour demandé n’est pas une panne. L’horizon par défaut est de 31 jours.

## Conditions avant V4.4

- plusieurs jours de rafraîchissement modèle seul stables ;
- aucun doublon de prédiction ;
- calendrier suffisamment couvert ;
- revue des cold-start ;
- protocole de validation marché et plafond de crédits approuvés.
