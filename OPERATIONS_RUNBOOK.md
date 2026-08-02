# Runbook V3.7 — opérations depuis le navigateur

## Déployer

```text
GitHub → Actions → Deploy production → Run workflow
```

Conserver `deploy_web`, `deploy_cron` et `verify_browser` activés. Le workflow échoue si les tests, Railway, `/api/release` ou Chromium ne confirment pas la release.

## Vérifier sans déployer

```text
GitHub → Actions → Verify production → Run workflow
```

La branche sélectionnée sert de référence pour la version, le commit et le hash du modèle.

## Reconstruire le modèle football

```text
GitHub → Actions → Rebuild fresh football model → Run workflow
```

Le workflow teste, commit les artefacts générés, déploie les deux services et vérifie l’API puis l’interface lorsque la configuration Railway est complète.

## Préparer le benchmark historique

```text
GitHub → Actions → Historical validation sample → Run workflow
mode = plan_only
```

Ce mode consomme zéro crédit. Les limites absolues de la V3.7 sont : 30 événements, 31 appels de découverte et 200 crédits de snapshots.

## Exécuter le petit lot

Relancer le même workflow avec :

```text
mode = execute_sample
sample_events ≤ 30
max_discovery_calls ≤ 31
max_odds_credits ≤ 200
confirmation = EXECUTE_SAMPLE
```

## Sauvegarder PostgreSQL

```text
GitHub → Actions → Backup and verify database → Run workflow
```

Le run exporte une sauvegarde logique, la restaure dans une base temporaire, la chiffre, supprime le clair et publie uniquement le fichier chiffré.

## Restaurer le modèle d’un ancien commit

1. Dans l’historique GitHub, copier le SHA du commit qui contient le modèle connu comme bon.
2. Ouvrir :

```text
GitHub → Actions → Rollback model release → Run workflow
```

3. Renseigner ce SHA dans `source_commit` et saisir exactement `ROLLBACK`.

Le workflow restaure le modèle, les métriques, le manifeste et `data/real/football_active.csv`, exécute les tests, crée un nouveau commit, déploie et vérifie Chromium.

## Préparer une nouvelle conversation

```text
GitHub → Actions → Generate handoff package → Run workflow
```

Télécharger l’artefact `sports-prediction-handoff-v3.7` et le joindre directement dans la nouvelle conversation.
