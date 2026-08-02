# Hotfix V3.2.1 — faux statut « API indisponible »

## Symptôme

Après connexion, la page s'affiche mais montre :

- le badge `API indisponible` ;
- une notification `can't access property "toFixed", ci[0] is undefined`.

## Cause

L'API répond correctement. Le frontend reçoit un benchmark `not_run` sans intervalle de confiance, puis tente d'appeler `toFixed()` sur `ci[0]` et `ci[1]` alors que le tableau est vide.

Le bloc global d'initialisation assimilait ensuite toute erreur JavaScript secondaire à une panne de l'API.

## Corrections

- vérification que `ci95` contient exactement deux nombres avant formatage ;
- séparation du test `/api/health` du reste du rendu ;
- une erreur de composant n'écrase plus le statut de santé de l'API ;
- ajout de `?v=3.2.1` au script pour contourner le cache navigateur ;
- test de non-régression.

## Déploiement

Remplacer au minimum :

- `static/app.js`
- `static/index.html`
- `webapp.py`

Puis commit/push et lancer `Deploy Latest Commit` dans Railway. Après déploiement, effectuer un rechargement forcé du navigateur.
