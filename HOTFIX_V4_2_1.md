# Hotfix V4.2.1 — rendu du préflight frontend

## Incident

Le dashboard V4.2.0 affichait le toast :

```text
Interface partiellement chargée : pct is not defined
```

Le formateur `pct` était déclaré dans la portée locale de `renderEvidence`, puis appelé par `renderPreflight`. Le préflight échouait donc au runtime alors que le rapport evidence continuait de s’afficher.

## Correction

- `pct` devient un utilitaire partagé au niveau du module JavaScript.
- Le cache de l’asset passe à `app.js?v=4.2.1`.
- Un test Node exécute réellement `renderPreflight` avec une couverture et un intervalle Wilson.
- Le smoke test Chromium attend désormais le panneau préflight et échoue sur tout toast `Interface partiellement chargée`.

## Impact

Aucun changement de backend, de modèle, de base, de campagne, de budget ou de logique statistique.
