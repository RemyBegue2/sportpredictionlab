# Sports Prediction Lab V4.5 — Automated Shadow Learning

Application privée de recherche football et tennis. La vue principale montre seulement les matchs, les probabilités, les signaux shadow et la prochaine action. Les panneaux techniques sont chargés uniquement après activation du **mode expert**.

## Parcours quotidien

```text
Calendrier gratuit → probabilités modèle → capture marché plafonnée
→ signal shadow ou abstention → règlement → bankroll fictive
→ challenger hebdomadaire → revue humaine du champion
```

## Vue simple

La page d’accueil est organisée autour de trois sections :

1. **Aujourd’hui** — matchs et probabilités ;
2. **Signaux** — écarts modèle–marché expérimentaux et simulations repliées ;
3. **Apprentissage** — progression, champion, challenger, budget et prochaine action.

Le mode expert conserve le centre de contrôle, la qualité des données, les campagnes historiques, les modèles manuels et l’audit.

## Garde-fous par défaut

```text
DAILY_ODDS_ENABLED=false
DAILY_ODDS_MAX_CREDITS=0
SHADOW_MODE_ENABLED=false
AUTOMATED_SHADOW_ENABLED=false
HISTORICAL_EVIDENCE_ENABLED=false
```

L’ouverture du dashboard ne déclenche aucun appel fournisseur. L’automatisation exige simultanément le marché live, le mode shadow, un plafond quotidien et la variable GitHub correspondante.

## Endpoints principaux

```text
/api/daily/slate
/api/research-lab
/api/research-lab/learning
/api/research-lab/refresh
/api/research-lab/settle
/api/research-lab/optimise
/api/research-lab/champion/promote
/api/model-diagnostics
/api/credit-firewall
/api/release
/api/ready
```

## Workflows V4.5

```text
Automated shadow learning cycle
Promote approved research champion
Deploy production
Verify production
Refresh daily product
```

La capture et le règlement partagent le même plafond journalier. L’entraînement hebdomadaire ne consomme aucun crédit. La promotion est exclusivement manuelle et ne déclenche ni pari ni mise.

## Validation

- 235 tests collectés et réussis par lots disjoints ;
- couverture globale combinée avec branches : 78,3 % (83,0 % des instructions) ;
- syntaxe Python, JavaScript et YAML validée ;
- aucun appel réel à The Odds API pendant la préparation ;
- aucune affirmation de rentabilité.

## Documents V4.5

- `UPGRADE_V4_5.md`
- `AUDIT_MULTI_ROLES_V4_5.md`
- `RESULTATS_V4_5.md`
- `KNOWN_ISSUES_AND_GATES_V4_5.md`
- `OPERATIONS_RUNBOOK_V4_5.md`
- `VALIDATION_V4_5.json`
