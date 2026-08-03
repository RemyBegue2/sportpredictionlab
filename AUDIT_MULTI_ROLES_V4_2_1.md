# Audit multi-rôles — Sports Prediction Lab V4.2.1

## Verdict consolidé

- **Hotfix frontend : GO**
- **Déploiement contrôlé : GO**
- **Relance du préflight : attendre le déploiement V4.2.1**
- **Stage 100 : toujours NO-GO**

## Frontend Engineer

Cause reproduite : `pct` était limité à `renderEvidence` et inaccessible depuis `renderPreflight`. Le correctif déplace le formateur dans la portée partagée.

## QA

Les anciens tests vérifiaient uniquement la présence des sélecteurs et chaînes dans `app.js`. Ils ne déclenchaient jamais le rendu du préflight. Un test Node exécute maintenant le chemin runtime exact. Un test Chromium renforcé exige aussi un rendu réel du panneau préflight et refuse tout chargement partiel.

## SRE / Release

La version passe à 4.2.1 afin d’invalider le cache navigateur. Les workflows attendent la même version. Aucun changement n’est apporté au mécanisme Railway stabilisé avec `--detach` et vérification publique.

## Product Owner

Le hotfix reste strictement ciblé : aucune modification de l’expérience evidence, des seuils ou des données.

## Data Engineer / Quant / Statisticien

Aucun impact sur les rapports, les calculs de couverture, les plans candidats, les baselines ou les portes statistiques.

## Sécurité

Aucune dépendance externe ajoutée, aucune route rendue publique et aucune donnée sensible exposée.

## Usage responsable

Les invariants restent inchangés : aucune mise, aucun pari automatique, aucune promotion automatique et aucune affirmation de rentabilité.

## Conclusion

La régression était une erreur frontend réelle et visible, sans corruption de données. La V4.2.1 corrige la portée JavaScript et ferme le trou de test qui avait laissé passer l’incident.
