# Runbook opérationnel — V4.8.0

## Déploiement fermé

```text
DAILY_ODDS_ENABLED=false
DAILY_ODDS_MAX_CREDITS=0
SHADOW_MODE_ENABLED=false
AUTOMATED_SHADOW_ENABLED=false
HISTORICAL_EVIDENCE_ENABLED=false
```

Le pre-deploy doit exécuter :

```bash
python -m scripts.db_migrate
```

Vérifier ensuite :

```text
/api/ready                   ready
/api/release                 version 4.8.0
/api/evidence-acceleration   collecting, hold ou review_required
```

## Interface simple

1. Aujourd’hui est seul visible au démarrage.
2. La carte `À retenir` contient une synthèse, pas un JSON.
3. Signaux remplace Aujourd’hui.
4. Apprentissage affiche quatre cartes seulement.
5. Aucune liste simple ne dépasse huit cartes.
6. Le mode expert charge les détails à la demande.
7. Aucun toast rouge ne doit apparaître.

## Evidence Acceleration

Workflow :

```text
Run evidence acceleration
confirmation: RUN_EVIDENCE_ACCELERATION
```

Attendus avec les données livrées :

```text
football.status = hold_explained
tennis.catalog.readiness.status = collecting
limits.provider_credits_consumed = 0
limits.automatic_promotion = false
```

Ne pas abaisser les seuils tennis pour obtenir artificiellement un candidat.

## Import tennis

```bash
python -m scripts.import_tennis_dataset \
  --input data/imports/tennis.csv \
  --output-dir artifacts/tennis_import \
  --source <source_documentée> \
  --license-status research_only
```

Contrôler :

- `accepted.csv` ;
- `quarantined.csv` ;
- `catalog.json` ;
- doublons ;
- classements futurs ;
- surfaces inconnues ;
- lineage héritée.

## Test public longue session

Workflow :

```text
Verify public long session
base_url: URL publique
 duration_seconds: 1800
```

Attendus :

- `status = ok` ;
- aucune erreur console/page ;
- `dom_growth` sous le seuil ;
- `resource_growth` sous le seuil ;
- un seul panneau actif ;
- version 4.8.0 ;
- rapport `public_long_session_v4_8.json`.

Ce test ne consomme aucun crédit fournisseur.

## Incident migration

1. ne pas relancer plusieurs déploiements en parallèle ;
2. consulter la révision Alembic ;
3. vérifier `dataset_catalog` et `holdout_generations` ;
4. conserver une sauvegarde avant tout downgrade ;
5. ne jamais supprimer manuellement une table en production ;
6. restaurer le champion et le produit quotidien indépendamment du laboratoire.

## Incident données tennis

- conserver le statut `collecting` ;
- examiner `quarantined.csv` ;
- corriger la source ou le mapping ;
- produire une nouvelle version du dataset ;
- ne pas écraser l’ancien dataset ;
- ne pas ouvrir The Odds API pour compenser un import incomplet.
