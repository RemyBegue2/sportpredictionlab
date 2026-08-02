# Sports Prediction Lab V3.4

Application privée de recherche football/tennis avec FastAPI, PostgreSQL, The Odds API, shadow mode immuable et reconstruction football multi-saisons.

## Nouveautés V3.4

- écran « Pourquoi zéro ? » pour chaque cycle shadow ;
- entonnoir détaillé des exclusions ;
- durée et quota avant/après ;
- verrou anti-chevauchement PostgreSQL ;
- pipeline de téléchargement et normalisation Premier League 2021-2026 ;
- candidat séparé du modèle actif ;
- règles de promotion chronologiques ;
- workflow GitHub Actions manuel et hebdomadaire ;
- Dockerfile qui conserve les artefacts vérifiés au lieu de réentraîner le vieux snapshot.

## Déploiement Railway

Remplacer le dépôt par cette version et pousser. Les services web et `shadow-cron` existants peuvent continuer à utiliser leurs fichiers `railway.toml` et `railway.cron.toml`.

Mettre à jour, sur les deux services :

```text
MODEL_VERSION=3.4.0
```

Le pre-deploy crée automatiquement la table `shadow_cycle_diagnostics`.

## Reconstruction fraîche

Utiliser le workflow GitHub **Rebuild fresh football model**. Voir [FRESH_DATA_REBUILD_GUIDE.md](FRESH_DATA_REBUILD_GUIDE.md).

## Démarrage local

```bash
pip install -r requirements.txt
python -m scripts.ensure_artifacts
uvicorn webapp:app --reload
```

## Limites

Le modèle livré dans l'archive reste l'ancien snapshot tant que le workflow de reconstruction n'a pas produit et promu un candidat. Le produit ne place jamais de pari et ne promet aucun gain.
