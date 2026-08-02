# Model Card V3.5

## Football 1N2

Le modèle réellement chargé est identifié par :

- `model_id` ;
- `model_version` ;
- SHA-256 de l’artefact ;
- SHA-256 du dataset ;
- date limite d’entraînement ;
- statut de cycle de vie ;
- métriques hors échantillon disponibles.

Ces éléments sont exposés dans `/api/system/status` et `artifacts/release_manifest.json`.

## Cycle de vie

```text
candidate → shadow → active → degraded → retired
```

Les transitions sont enregistrées avec l’ancien statut, le nouveau statut, le motif, l’acteur et l’heure. Un redémarrage de l’application ne doit pas réinitialiser le statut.

## Critères de promotion

La fraîcheur et un workflow réussi ne suffisent pas. La promotion doit considérer :

- validation chronologique ;
- log-loss et calibration ;
- baseline naïve ;
- comparaison Winamax/consensus ;
- stabilité sur plusieurs périodes ;
- absence de fuite temporelle ;
- taille d’échantillon.

## Tennis

Le tennis reste expérimental et non calibré. Aucun statut `active` ne doit lui être attribué dans l’état actuel.

## Usages interdits

- placement automatique ;
- recommandation de mise ;
- promesse de rendement ;
- réécriture d’anciennes prédictions avec un modèle plus récent.
