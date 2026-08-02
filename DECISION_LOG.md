# Journal des décisions V3.5

1. La preuve de déploiement vient du conteneur exposé, pas du statut du workflow.
2. `/api/release` est public mais minimal et sans secret.
3. `/api/system/status` reste privé.
4. Le statut modèle est explicite et ne change pas au redémarrage.
5. Un seul modèle peut être `active` par sport.
6. Les anciennes prédictions restent liées à leur version originale.
7. Les métriques sont séparées par modèle et horizon.
8. Les artefacts frais du dépôt utilisateur ne doivent pas être remplacés par une archive locale obsolète.
9. Le rollback restaure des artefacts, pas l’historique de prédictions.
10. Le backup portable complète, mais ne remplace pas, les backups managés Railway.
11. Aucun pari automatique ni taille de mise ne sera ajouté.
12. L’export de conversation suit une liste blanche et n’inclut aucun secret.
