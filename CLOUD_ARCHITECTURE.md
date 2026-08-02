# Architecture cloud V3.7

```text
Utilisateur (navigateur)
├── GitHub Actions
│   ├── Deploy production
│   ├── Verify production
│   ├── Rebuild fresh football model
│   ├── Historical validation sample
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
