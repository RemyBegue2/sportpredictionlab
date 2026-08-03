# Architecture cloud V3.7

```text
Utilisateur (navigateur)
├── GitHub Actions
│   ├── Deploy production
│   ├── Verify production
│   ├── Rebuild fresh football model
│   ├── Estimate historical sample / Run historical sample
│   ├── Backup and verify database
│   ├── Rollback model release
│   └── Generate handoff package
└── Railway
    ├── sportpredictionlab   FastAPI + interface privée
    ├── shadow-cron          collecte et règlement shadow
    ├── historical-worker    réservé aux travaux historiques longs
    └── PostgreSQL           audit, checkpoints, modèles et métriques
```

Le PC utilisateur n’exécute aucun script. GitHub Actions fournit l’environnement Python éphémère et Railway fournit les services permanents.

Un déploiement est validé selon quatre niveaux :

1. tests du dépôt ;
2. build Railway ;
3. preuve `/api/release` version + commit + hash du modèle ;
4. ouverture obligatoire de l’interface privée dans Chromium lorsque `verify_browser=true` (valeur par défaut).

## V3.8 — exécution historique isolée

Le petit lot historique s'exécute sur un runner GitHub Actions isolé. Il n'utilise ni le processus web ni le cron Railway. PostgreSQL conserve les jobs, checkpoints et métriques. Après publication du rapport, le service web Railway est redéployé et vérifié via `/api/release`.

Cette architecture évite d'ajouter un troisième service Railway uniquement pour un traitement ponctuel plafonné.
