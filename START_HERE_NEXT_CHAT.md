# START HERE — Sports Prediction Lab V3.9

## État actuel

- Version cible : **3.9.0 Data Reliability & Coverage Funnel**.
- Exploitation : GitHub Actions + Railway, aucun Python local.
- Modèle : inchangé par la V3.9.
- Dernier lot observé avant recalcul : 111 événements découverts, 10 avec cotes, 63 lignes acceptées, 100 crédits.
- Problème corrigé : le rapport V3.8 divisait les événements avec cotes par tout le vivier découvert, y compris les événements jamais sélectionnés à cause du budget.

## Première action dans une nouvelle conversation

Lire dans cet ordre :

1. `handoff/HANDOFF_CURRENT.md`
2. `handoff/HANDOFF_CURRENT.json`
3. `AUDIT_MULTI_ROLES_V3_9.md`
4. `KNOWN_ISSUES_AND_GATES.md`
5. le dernier log GitHub en cas d’échec

## Première action opérationnelle

```text
GitHub
→ Actions
→ Recompute latest evidence
→ Run workflow
```

Ce workflow doit consommer zéro crédit fournisseur.

## Règles non négociables

- aucune commande Python locale ;
- aucune mise conseillée ;
- aucun pari automatique ;
- aucune promotion automatique de modèle ;
- aucune nouvelle collecte payante avant lecture du funnel V3.9 corrigé.
