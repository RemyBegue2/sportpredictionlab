# Risques et portes V3.9

## Porte 1 — Artefact historique disponible

Le recalcul zéro crédit exige un artefact GitHub non expiré nommé `historical-sample-evidence-*`.

## Porte 2 — Intégrité technique

Bloquants :

- aucune ligne historique ;
- violation temporelle ;
- plus de 1 % de doublons ;
- backfill incomplet ;
- plafond de crédits dépassé.

## Porte 3 — Couverture fournisseur

Calculée uniquement sur les cibles exécutées. Seuil de contrôle : 95 %.

## Porte 4 — Matching

Calculé uniquement sur les événements retournés. Seuil de contrôle : 95 %.

## Porte 5 — Consensus

Disponible si au moins 70 % des cibles exécutées possèdent deux marchés bookmaker complets.

## Porte 6 — Winamax

Disponible si au moins 70 % des cibles exécutées possèdent un marché Winamax complet. Cette porte ne bloque pas une analyse du consensus.

## Porte 7 — Preuve statistique

Moins de 100 événements : aucune conclusion sur le modèle.

## Décision actuelle

Ne pas lancer de nouvelle collecte payante avant d’avoir exécuté le recalcul V3.9 et lu le funnel corrigé.
