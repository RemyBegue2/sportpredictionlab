# Reconstruction football fraîche — V3.5

Le workflow `.github/workflows/rebuild-fresh-football.yml` télécharge les saisons configurées, entraîne un candidat, applique les portes chronologiques, exécute les tests, génère la preuve de release et exporte le handoff.

## Lancement

```text
GitHub → Actions → Rebuild fresh football model → Run workflow
```

## Ordre du workflow

1. téléchargement et normalisation ;
2. entraînement du candidat ;
3. décision de promotion ;
4. tests ;
5. `release_manifest.json` ;
6. export du handoff ;
7. commit des artefacts générés ;
8. déploiement Railway si les identifiants sont configurés ;
9. vérification de `/api/release` si `APP_PUBLIC_URL` est configurée.

## Interprétation

- workflow vert : le pipeline et les tests ont réussi ;
- `promoted=false` : les portes statistiques n’ont pas toutes été franchies ;
- déploiement vérifié : `/api/release` correspond au commit et au hash attendus ;
- modèle `shadow` : observation uniquement ;
- modèle `active` : transition administrative explicite et auditée.

Une promotion offline ne démontre pas un avantage contre Winamax ou le consensus.
