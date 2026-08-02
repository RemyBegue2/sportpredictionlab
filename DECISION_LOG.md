# Journal des décisions

## V3.7

1. L’exploitation normale ne dépend plus de Python installé sur le PC.
2. GitHub Actions est l’interface d’exécution ; Railway est la plateforme d’hébergement.
3. Un déploiement n’est réussi qu’après preuve version + commit + hash du modèle.
4. Le test navigateur est obligatoire par défaut ; si `verify_browser=true`, l’absence de `APP_PASSWORD` bloque le workflow.
5. Le benchmark historique initial reste limité à 30 événements.
6. `plan_only` précède toujours `execute_sample`.
7. Une sauvegarde doit être restaurée avant d’être publiée comme artefact valide.
8. Les rollbacks exigent un commit Git source connu et la confirmation exacte `ROLLBACK`.
9. Les critères champion–challenger V3.6 ne sont pas assouplis.
10. Aucun pari ou staking automatique n’est ajouté.
