# Architecture cloud V3.5

```text
GitHub Actions
├── rebuild football
├── tests
├── release_manifest.json
├── handoff export
├── commit des artefacts générés
├── railway up
└── /api/release post-deploy verification

Railway
├── sportpredictionlab
│   ├── FastAPI
│   ├── interface privée
│   ├── /api/release public minimal
│   └── /api/system/status privé
├── shadow-cron
│   └── cotes → prédictions figées → résultats → règlement
└── PostgreSQL
    ├── prédictions et snapshots
    ├── model_registry
    ├── model_status_transitions
    └── release_registry
```

La release, le modèle et le dataset sont reliés par hashes. Le déploiement n’est considéré prouvé qu’après interrogation du conteneur public.
