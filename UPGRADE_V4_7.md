# Upgrade V4.6.0 → V4.7.0

## Changements

- stabilité longue session : déduplication, timeout, annulation et retry expert ;
- listes simples plafonnées à huit cartes ;
- quatre indicateurs d’apprentissage seulement ;
- Challenger Factory football/tennis à zéro crédit ;
- datasets hashés et paramètres portables ;
- endpoint et workflow dédiés ;
- smoke navigateur renforcé par navigation répétée ;
- frontend `app.js?v=4.7.0`.

## Application

```bash
git apply sportpredictionlab-v4.7.0.patch
git add .
git commit -m "Add stable cockpit and sport challenger factory"
git push
```

Déployer avec `verify_browser=true`, puis vérifier `/api/challenger-factory`.

## Compatibilité

Aucune migration de schéma n’est nécessaire. La Challenger Factory utilise le registre append-only existant. Les plafonds et garde-fous V4.6 restent inchangés.
