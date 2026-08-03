# Runbook V4.0 — navigateur uniquement

## Déploiement normal

1. `Actions → Deploy production`.
2. Conserver web, cron et test navigateur activés.
3. Vérifier `/api/release` et le badge `v4.0.0`.

## Préparer une campagne sans crédit

1. `Actions → Run evidence campaign`.
2. Mode `dry_run`.
3. Choisir 30, 100, 300 ou 1 000.
4. Fixer le plafond maximal acceptable.
5. Télécharger l’artefact `evidence-campaign-plan-*`.

## Exécuter le premier stage

1. Mode `start_next_stage`.
2. Stage 30.
3. Baseline `consensus`.
4. Confirmation `EXECUTE_CAMPAIGN`.
5. Lire le résumé avant de passer au stage suivant.

## Reprendre une campagne interrompue

1. Utiliser `continue_current_stage` avec exactement le même stage, budget et baseline.
2. Le workflow recherche un checkpoint GitHub non expiré.
3. Une incompatibilité n’est jamais contournée silencieusement.

## Recalcul sans fournisseur

Mode `recompute_only`. Il reconstruit le rapport de campagne depuis le dernier rapport de preuve commité et redéploie le dashboard. Aucun appel The Odds API.

## Critères avant le stage suivant

- zéro violation temporelle ;
- zéro doublon ;
- couverture fournisseur ≥ 80 % ;
- matching fiable ≥ 95 % ;
- couverture consensus ≥ 70 %.

## En cas d’échec

- échec avant `Discover historical events` : aucun crédit consommé ;
- échec pendant la collecte : télécharger l’artefact de checkpoint puis relancer `continue_current_stage` ;
- artefact expiré ou incompatible : le workflow annonce un démarrage frais ;
- erreur de déploiement : la collecte reste dans l’artefact GitHub, mais le dashboard Railway peut rester sur l’ancienne version.
