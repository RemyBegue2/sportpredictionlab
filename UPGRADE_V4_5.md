# Upgrade V4.4.0 → V4.5.0

## Changements

- interface simple par défaut avec mode expert à la demande ;
- sections principales Aujourd’hui, Signaux et Apprentissage ;
- chargement différé des endpoints experts ;
- trajectoires de bankroll fictive auditables ;
- registre quotidien partagé des crédits capture/règlement ;
- automatisation conditionnelle capture, règlement et entraînement ;
- challenger stable `RCH-*` ;
- portes de promotion plus strictes ;
- workflow manuel de promotion.

## Variables nouvelles

```text
AUTOMATED_SHADOW_ENABLED=false
RESEARCH_PROMOTION_MIN_EVENTS=100
RESEARCH_PROMOTION_MIN_HOLDOUT_SIGNALS=20
RESEARCH_PROMOTION_MIN_EVENTS_PER_SPORT=60
RESEARCH_PROMOTION_MAX_DRAWDOWN=0.25
```

## Procédure

1. appliquer le patch V4.5 ;
2. commit et push ;
3. déployer avec vérification navigateur ;
4. contrôler la version 4.5.0 ;
5. vérifier la vue simple ;
6. ouvrir puis refermer le mode expert ;
7. conserver l’automatisation désactivée pendant la vérification initiale ;
8. suivre `OPERATIONS_RUNBOOK_V4_5.md` avant une activation payante.

Aucune migration de schéma n’est nécessaire : la V4.5 réutilise les journaux append-only existants.
