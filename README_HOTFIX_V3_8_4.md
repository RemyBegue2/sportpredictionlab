# Hotfix cumulatif V3.8.4 — workflow historique sans identifiant manuel

Ce correctif remplace les hotfixes V3.8.1 à V3.8.3 et supprime définitivement la recopie manuelle du `REQ-...`.

## Cause du dernier échec

Le workflow comparait le plan recalculé avec un champ texte saisi dans GitHub. Un caractère invisible pouvait faire échouer la comparaison alors que les deux identifiants affichés étaient identiques.

## Nouveau parcours

1. `Estimate historical sample` reste facultatif et ne consomme aucun crédit.
2. `Run historical sample` ne demande plus de `plan_request_id`.
3. Il recalcule et journalise lui-même son plan interne.
4. La seule confirmation demandée est `EXECUTE_SAMPLE`.
5. Un verdict de qualité bloqué est publié comme résultat analytique, pas comme panne technique.

## Installation

Décompresser le ZIP à la racine du dépôt et accepter les remplacements, puis créer un nouveau commit.

Commit conseillé :

`Fix historical workflow end-to-end v3.8.4`

Lancer ensuite une nouvelle exécution :

`Actions → Run historical sample → Run workflow`

Paramètres recommandés pour le premier lot :

- start_date : `2023-01-01`
- end_date : `2026-07-31`
- sample_events : `30`
- max_discovery_calls : `14`
- max_odds_credits : `120`
- confirmation : `EXECUTE_SAMPLE`

Ne pas utiliser `Re-run jobs` sur une ancienne exécution, car elle conserve l'ancien workflow.

## Validation locale

- 128 tests réussis
- 9 workflows YAML valides
- compilation Python réussie
- plan exact 2023-01-01 → 2026-07-31 : 14 appels de découverte, 12 snapshots maximum dans 120 crédits

Aucun appel fournisseur et aucun crédit The Odds API n'ont été consommés pendant cette validation locale.
