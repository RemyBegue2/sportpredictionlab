# Hotfix CI V3.7

## Problème corrigé

Le workflow GitHub définit `RAILWAY_ENVIRONMENT=production` pour cibler Railway.
Les tests de migration copiaient cette variable dans leurs sous-processus et le code
les prenait à tort pour des processus exécutés *dans* Railway. Une base SQLite de test
était alors rejetée.

## Correctif

- distingue une cible Railway distante d'un vrai runtime Railway ;
- utilise `RAILWAY_SERVICE_ID` / `RAILWAY_ENVIRONMENT_ID` comme marqueurs de runtime ;
- conserve le refus de SQLite dans un vrai service cloud ;
- ajoute un test de non-régression pour GitHub Actions.

## Installation sans Python local

Copier les trois dossiers de cette archive à la racine du dépôt GitHub et accepter le
remplacement des fichiers. Créer un commit, puis lancer une nouvelle exécution de
`Deploy production` depuis l'onglet Actions.

## Validation

Suite complète exécutée après application : `109 passed`.
