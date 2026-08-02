# Handoff V3.6

Exécuter dans le vrai dépôt après chaque commit ou déploiement :

```bash
python -m scripts.generate_release_manifest
python -m scripts.export_handoff
```

Les fichiers générés localement dans le paquet ont un commit `unknown`. Ils servent de structure de reprise, pas de preuve du dépôt GitHub/Railway de l’utilisateur. Le vrai dépôt doit les régénérer.
