# Résultats de validation — V4.2.1

## Tests

La suite complète a été exécutée en quatre lots disjoints :

- lot 1 : 37 tests réussis ;
- lot 2 : 42 tests réussis ;
- lot 3 : 55 tests réussis ;
- lot 4 : 50 tests réussis ;
- total : **184 réussis, 0 échec**.

La commande monolithique `pytest -q` a dépassé la limite de l’environnement après 39 %, sans échec observé avant l’arrêt. La validation complète repose donc sur les quatre lots couvrant tous les fichiers de tests exactement une fois.

## Validation frontend

- `node --check static/app.js` : réussi ;
- test Node du rendu `renderPreflight` : réussi ;
- test Chromium isolé avec le moteur système : rendu `Viable`, couverture `75.0 %`, aucune erreur de page ;
- smoke test de production renforcé pour vérifier le panneau préflight et refuser un toast de chargement partiel.

## Autres validations

- compilation Python : réussie ;
- 12 workflows GitHub Actions et `render.yaml` : YAML valide ;
- version application : `4.2.1` ;
- version paquet : `0.4.2.1`.

Aucun appel The Odds API, aucun crédit fournisseur et aucun déploiement Railway n’ont été exécutés dans l’environnement de préparation.
