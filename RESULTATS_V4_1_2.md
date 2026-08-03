# Résultats vérifiés — V4.1.2

- Régression exacte `tests/test_v411_hotfix.py + tests/test_webapp.py` : 11 réussis.
- Suite principale hors tests d'entrypoints : 152 réussis.
- Tests d'entrypoints de déploiement : 10 réussis.
- Total validé par lots : 162 réussis, 0 échec.
- Compilation Python : réussie.
- Syntaxe JavaScript : réussie.
- YAML : 13 fichiers chargés avec succès.
- Aucun changement du schéma de base de données.
- Aucun appel fournisseur et aucun crédit consommé.

La suite monolithique peut bloquer dans cet environnement isolé sur certains sous-processus des tests d'entrypoints ; ces 10 tests passent séparément. Le défaut observé sur GitHub Actions a, lui, été reproduit et corrigé dans un même processus de test.
