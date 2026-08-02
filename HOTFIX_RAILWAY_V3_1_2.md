# Hotfix Railway V3.1.2

## Symptôme

```text
ModuleNotFoundError: No module named 'sports_predictor'
```

Le traceback observé référençait l'import à la ligne 5, ce qui prouve que le fichier réellement construit par Railway n'était pas le script V3.1.1 attendu.

## Défense en profondeur

La V3.1.2 ne dépend plus d'un seul mécanisme :

1. un fichier Python `.pth` ajoute durablement `/app` au chemin d’import dans l’image, sans téléchargement supplémentaire.
2. L'image définit `PYTHONPATH=/app`.
3. La commande Railway exécute explicitement depuis `/app`.
4. `db_migrate.py` ajoute toujours la racine du dépôt à `sys.path`.
5. Un test lance la migration depuis un répertoire de travail extérieur au projet.

## Contrôle dans GitHub

Le fichier `scripts/db_migrate.py` déployé doit contenir `ROOT = Path(__file__).resolve().parents[1]` avant l'import de `sports_predictor`. Le `Dockerfile` doit contenir `PYTHONPATH=/app` et `sports_prediction_lab.pth`.
