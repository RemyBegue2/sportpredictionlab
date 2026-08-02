# Sports Prediction Lab V3.5

Application privée de recherche football/tennis avec FastAPI, PostgreSQL, The Odds API, shadow mode pré-match et preuve opérationnelle de chaque déploiement.

## Ce que V3.5 ajoute

- endpoint public minimal `/api/release` pour vérifier version, commit et hash du modèle après déploiement ;
- endpoint privé `/api/system/status` consolidant release, modèles, base, cron, benchmark et continuité ;
- registre de releases PostgreSQL ;
- cycle de vie explicite des modèles : `candidate → shadow → active → degraded → retired` ;
- métriques shadow séparées par modèle, version et horizon ;
- manifeste `artifacts/release_manifest.json` sans secret ;
- snapshot et rollback de modèles avec contrôle SHA-256 ;
- export de reprise `handoff/HANDOFF_CURRENT.md` et `.json` ;
- backup applicatif portable et restauration vers une base vide ;
- chargement frontend indépendant par section : une API secondaire en erreur ne bloque plus toute la page ;
- smoke test post-déploiement GitHub Actions lorsque `APP_PUBLIC_URL` est configurée.

## Mise à niveau depuis V3.4.4

**Ne remplacez pas les artefacts frais générés dans votre dépôt.** Le paquet d’upgrade V3.5 omet volontairement :

```text
artifacts/*.joblib
data/real/
```

Décompressez l’upgrade à la racine du dépôt, puis :

```bash
git add -A
git commit -m "Upgrade to V3.5 operational evidence"
git push
```

Mettez `MODEL_VERSION=3.5.0` sur `sportpredictionlab` et `shadow-cron`, puis déployez le dernier commit.

## Vérification immédiate

```text
GET /api/health
GET /api/release
```

Résultat attendu :

```json
{
  "status": "ok",
  "version": "3.5.0",
  "artifact_integrity_ok": true
}
```

L’endpoint `/api/release` est volontairement public et ne contient aucun secret. Le détail complet reste protégé dans `/api/system/status`.

## Handoff pour une nouvelle conversation

```bash
python -m scripts.generate_release_manifest
python -m scripts.export_handoff
```

Joindre ensuite :

```text
START_HERE_NEXT_CHAT.md
handoff/HANDOFF_CURRENT.md
handoff/HANDOFF_CURRENT.json
artifacts/release_manifest.json
```

Le générateur n’exporte ni variables d’environnement, ni clé API, ni mot de passe, ni `DATABASE_URL`.

## Rollback d’un modèle

Créer un snapshot avant promotion :

```bash
python -m scripts.snapshot_release --release-id before-new-model
```

Vérifier un rollback sans modifier les fichiers :

```bash
python -m scripts.rollback_release --release-id before-new-model
```

Exécuter réellement :

```bash
python -m scripts.rollback_release --release-id before-new-model --execute
```

Le rollback ne remplace pas le code Railway. Il restaure les artefacts et le dataset actif, puis régénère la preuve de release.

## Backup applicatif

```bash
python -m scripts.portable_db_backup --backup
```

Pour tester une restauration, utilisez impérativement une base vide distincte :

```bash
python -m scripts.portable_db_backup \
  --restore \
  --file backups/portable-YYYYMMDDTHHMMSSZ.json.gz \
  --database-url postgresql+psycopg://... 
```

La commande est un dry-run tant que `--execute` n’est pas ajouté. Elle ne remplace pas les sauvegardes managées Railway.

## Limites

- aucune rentabilité n’est démontrée sans historique hors échantillon suffisant ;
- le tennis reste expérimental et non calibré ;
- aucune connexion au compte Winamax ;
- aucun pari automatique ;
- aucune recommandation de taille de mise ;
- une shortlist vide reste un résultat valide.
