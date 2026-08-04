# Upgrade V4.8.0 → V4.9.0

## Changements

- deux challengers football bornés et réellement entraînés ;
- zone de développement séparée du holdout déjà consulté ;
- nouvelle génération de holdout future ;
- import tennis incrémental versionné ;
- endpoint `/api/controlled-model-decision` ;
- workflow `Run controlled model decision` ;
- validation longue session séparée simple/expert ;
- vue Apprentissage simplifiée autour de football, tennis, production et coût ;
- version frontend `app.js?v=4.9.0`.

## Application

```bash
git apply sportpredictionlab-v4.9.0.patch
git add .
git commit -m "Add controlled model decision and live validation"
git push
```

## Déploiement

Déployer avec `verify_browser=true` et les dépenses fermées.

Vérifier :

```text
/api/release                     4.9.0
/api/ready                       ready
/api/controlled-model-decision   réponse JSON
```

Puis lancer :

```text
Run controlled model decision
Verify public long session
```

## Compatibilité

- aucune nouvelle migration de schéma n’est nécessaire ;
- les migrations Alembic V4.8 restent la baseline ;
- le champion actuel reste intact ;
- les anciens datasets restent lisibles ;
- les captures live restent désactivées par défaut ;
- aucun workflow V4.9 d’entraînement ne consomme de crédit fournisseur.
