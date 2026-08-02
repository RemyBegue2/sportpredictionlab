# Guide — reconstruction football fraîche

## Méthode recommandée : GitHub Actions

La V3.4 fournit `.github/workflows/rebuild-fresh-football.yml`.

1. Pousser la V3.4 sur GitHub.
2. Ouvrir l'onglet **Actions**.
3. Choisir **Rebuild fresh football model**.
4. Cliquer **Run workflow**.
5. Attendre la fin des tests et du commit automatique.
6. Railway redéploie le commit généré.

Le workflow télécharge les saisons 2021-22 à 2025-26, construit le dataset, entraîne un candidat, applique les règles de promotion et exécute les tests. Si une règle échoue, le rapport et le candidat sont conservés, mais le modèle actif n'est pas remplacé.

## Fichiers générés

- `data/real/epl_seasons/*.csv`
- `data/real/football_epl_2021_2026.csv`
- `artifacts/football_model_candidate.joblib`
- `artifacts/fresh_rebuild_report.json`
- `data/real/football_active.csv` uniquement après promotion
- `artifacts/football_model.joblib` uniquement après promotion

## Exécution locale

```bash
python -m scripts.rebuild_fresh_football --download
```

Pour autoriser la promotion automatique lorsque tous les contrôles passent :

```bash
python -m scripts.rebuild_fresh_football --download --promote
```

## Règles de promotion

- au moins 1 500 matchs ;
- au moins 250 matchs dans le test chronologique ;
- cutoff datant de moins de 240 jours ;
- log-loss finie ;
- log-loss meilleure que la baseline naïve ;
- ECE au plus égale à 0,15.

Ces règles ne prouvent pas un avantage contre Winamax. Elles autorisent seulement le passage du candidat au shadow mode actuel.
