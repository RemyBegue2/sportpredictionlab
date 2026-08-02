# Reprendre le projet dans une autre conversation

À la racine du dépôt :

```bash
python -m scripts.generate_release_manifest
python -m scripts.export_handoff
```

Joindre ensuite :

1. `START_HERE_NEXT_CHAT.md`
2. `handoff/HANDOFF_CURRENT.md`
3. `handoff/HANDOFF_CURRENT.json`
4. `artifacts/release_manifest.json`
5. le dernier log ou screenshot pertinent

Puis coller `NEXT_CHAT_PROMPT.txt`.

Le handoff ne contient aucun secret. La prochaine conversation doit néanmoins vérifier l’état réel via `/api/release` au lieu de supposer que le fichier local correspond au déploiement Railway.
