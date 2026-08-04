# Runbook opérationnel — V4.6.0

## Déploiement

Déployer avec les dépenses fermées :

```text
DAILY_ODDS_ENABLED=false
DAILY_ODDS_MAX_CREDITS=0
SHADOW_MODE_ENABLED=false
AUTOMATED_SHADOW_ENABLED=false
HISTORICAL_EVIDENCE_ENABLED=false
```

Vérifier :

```text
/api/ready          ready
/api/release        version 4.6.0
/api/feature-lab    collecting ou ready
```

## Interface simple

1. `Aujourd’hui` doit être le seul panneau visible au démarrage.
2. Cliquer `Signaux` : le panneau Aujourd’hui doit disparaître.
3. Cliquer `Apprentissage` : la fiabilité football et tennis doit apparaître.
4. Cliquer `Mode expert` : les diagnostics différés doivent se charger.
5. Aucun toast `Interface partiellement chargée` ne doit apparaître.

## Exécution du Feature Lab

Le laboratoire ne consomme aucun crédit.

Depuis GitHub Actions :

```text
Run calibration feature lab
```

Ou via l’API privée :

```text
POST /api/feature-lab/run
confirmation: RUN_FEATURE_LAB
```

Contrôler dans le rapport :

```text
limits.provider_credits_consumed = 0
limits.automatic_promotion = false
feature_lineage.valid = true
```

## Interprétation

- `collecting` : continuer à accumuler des résultats réglés ;
- `hold` : le calibrateur testé n’améliore pas suffisamment le holdout ;
- `candidate` : calibrateur acceptable pour revue, pas pour promotion automatique.

## Incident

Si le Feature Lab échoue :

- ne pas activer de fournisseur pour le réparer ;
- conserver le champion actuel ;
- consulter l’artefact GitHub ;
- vérifier le nombre d’événements, les dates et les manifests ;
- laisser le produit quotidien fonctionner.
