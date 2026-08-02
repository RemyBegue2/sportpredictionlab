# Résultats vérifiés V3.6

## Tests

```text
99 passed
```

## Couverture

```text
TOTAL 5608 statements, 845 missing, 85%
```

## Contrôles statiques

- 82 fichiers Python compilés sans erreur ;
- `node --check static/app.js` réussi ;
- workflow GitHub Actions YAML valide ;
- fichiers TOML Railway valides ;
- tous les sélecteurs JavaScript référencés existent dans le HTML.

## Fonctions validées

- benchmark multi-contenders sur protocole temporel identique ;
- classement par log-loss ;
- portes de promotion et interdiction de promotion automatique ;
- persistance d’une décision en base ;
- endpoint `/api/model-decision` ;
- plan historique immuable et détection de modification ;
- approbation exacte obligatoire pour un plan complet ;
- frontend « Décision modèle ».

## Non exécuté

- aucun appel historique The Odds API réel ;
- aucun backfill complet ;
- aucune preuve de supériorité face au marché ;
- aucun déploiement Railway réalisé depuis cet environnement.
