# Hotfix V3.7.3 — Browser smoke test / centre de contrôle

## Cause
Le test Chromium attendait seulement le badge `#health.ok`, puis lisait immédiatement
`#controlOverall`. Or le centre de contrôle était chargé dans un `Promise.allSettled`
avec des endpoints potentiellement plus lents. Le badge pouvait donc être prêt alors
que le centre affichait encore `—`.

## Correctif
- `static/app.js` charge `/api/control-center` indépendamment des autres endpoints.
- `scripts/browser_smoke_test.py` attend explicitement que `#controlOverall` ne soit
  plus vide ni égal à `—`.
- Le test inclut le message de l'interface en cas de véritable échec.
- Un test de non-régression vérifie ce contrat.

## Fichiers à remplacer
- `static/app.js`
- `scripts/browser_smoke_test.py`
- `tests/test_v37_cloud_control.py`

Créer un nouveau commit puis lancer une nouvelle exécution de `Deploy production`.
