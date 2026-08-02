# V3.4.4 — interface résiliente et déploiement fiable

## Causes corrigées

1. Le déploiement Railway était conditionné à une modification de `artifacts/` ou `data/real/`. Une correction de code seule pouvait donc passer les tests sans être déployée.
2. Un décalage de versions entre `index.html` et `app.js` pouvait produire un sélecteur DOM nul et interrompre le chargement de la page.

## Corrections

- Le workflow déploie tout commit courant lorsque les secrets Railway sont configurés, même si le modèle généré est identique.
- Sans secrets Railway, le workflow affiche un avertissement clair et reste réussi ; un déploiement manuel du dernier commit est alors requis.
- Le sélecteur DOM retourne un élément neutre journalisé lorsqu'un composant manque, évitant qu'un bloc secondaire casse toute l'interface.
- Le cache est invalidé avec `app.js?v=3.4.4`.
