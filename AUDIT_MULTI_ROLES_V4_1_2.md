# Audit multi-rôles — Hotfix V4.1.2

## Incident reproduit

Le workflow de déploiement V4.1.1 s'arrêtait pendant `pytest` avec 160 tests réussis et un échec sur `tests/test_webapp.py::test_readiness_and_prediction_history`.

Le test `test_startup_errors_are_logged_without_exception_details` injectait volontairement des erreurs de démarrage puis laissait `STARTUP_STATE` contaminé. Le test web suivant obtenait alors HTTP 503 alors que les contrôles vivants indiquaient une base connectée et des modèles disponibles.

## Corrections

- `/api/ready` utilise les contrôles vivants comme source de vérité.
- Une erreur de démarrage transitoire est effacée lorsque la dépendance correspondante est de nouveau saine.
- Le test de journalisation restaure `STARTUP_STATE` dans un bloc `finally`.
- Un test de régression vérifie qu'une readiness bloquée par des diagnostics obsolètes repasse à HTTP 200 après récupération.

## Revue par rôles

### Backend

GO. La readiness reflète désormais l'état courant plutôt qu'un verrou historique permanent.

### QA

GO. Le chemin exact qui échouait passe avec les deux fichiers de tests exécutés dans le même processus. Total validé par lots : 162 tests réussis, aucun échec.

### SRE

GO pour le pipeline de déploiement. Le correctif ne change ni le port, ni la commande de démarrage, ni la configuration Railway. `/api/ready` reste la sonde de readiness.

### Sécurité

GO. Les types d'erreurs peuvent rester journalisés, mais ni URL, ni identifiant, ni mot de passe ne sont exposés.

### Data / Quant / FinOps

Aucun changement. Le schéma, les modèles, les portes de preuve, le matching et la consommation fournisseur ne sont pas modifiés.

## Limites de validation

Aucun déploiement réel Railway n'a été effectué depuis cet environnement. La validation couvre le code, les tests, la syntaxe Python/JavaScript et les fichiers YAML.
