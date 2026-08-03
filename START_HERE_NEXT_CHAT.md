# Sports Prediction Lab — point de reprise V4.5.0

## État préparé

- Version : **4.5.0 — Automated Shadow Learning & Simple UI**.
- Vue simple : Aujourd’hui, Signaux, Apprentissage.
- Vue expert : chargée à la demande uniquement.
- Football et tennis : probabilités et signaux shadow de recherche.
- Bankrolls : simulations fictives avec trajectoires auditables.
- Automatisation : capture/règlement bornés et entraînement hebdomadaire sans crédit.
- Champion : promotion manuelle uniquement.
- Evidence historique : désactivée.

## Première action

1. Déployer V4.5.0 avec `verify_browser=true`.
2. Vérifier `/api/ready`, `/api/release`, `/api/research-lab` et `/api/research-lab/learning`.
3. Confirmer que la vue simple s’affiche avant le mode expert.
4. Garder `AUTOMATED_SHADOW_ENABLED=false` pendant la vérification initiale.
5. Suivre `OPERATIONS_RUNBOOK_V4_5.md` avant toute activation plafonnée.

## Règles

- un signal reste expérimental ;
- aucune bankroll réelle ni mise personnalisée ;
- aucun placement automatique ;
- aucun changement de seuil en cours d’échantillon ;
- promotion seulement après toutes les portes et une revue humaine ;
- aucune rentabilité future n’est revendiquée.
