# Sports Prediction Lab V3.9 — Data Reliability & Coverage Funnel

Application privée de recherche football/tennis avec FastAPI, Railway, PostgreSQL, The Odds API, shadow mode et moteur champion–challenger.

La V3.9 corrige le principal défaut du premier lot historique : les événements découverts mais non sélectionnés par le budget ne sont plus comptés comme des échecs fournisseur.

## Ce qui change

- funnel explicite : découvert → demandé → sélectionné → exécuté → retourné → rapproché → accepté ;
- couverture fournisseur calculée sur les cibles réellement exécutées ;
- matching calculé uniquement sur les événements réellement retournés ;
- portes séparées pour intégrité, fournisseur, matching, consensus, Winamax et preuve statistique ;
- matrice de couverture par bookmaker ;
- statut final pour chaque événement ;
- workflow **Recompute latest evidence** utilisant le dernier artefact GitHub sans nouvel appel The Odds API ;
- masquage des métriques V3.8 trompeuses tant que le recalcul V3.9 n’a pas été exécuté ;
- aucune dépendance à Python sur l’ordinateur de l’utilisateur.

## Parcours recommandé

```text
1. Copier l’upgrade V3.9 à la racine du dépôt GitHub
2. Définir MODEL_VERSION=3.9.0 sur sportpredictionlab et shadow-cron
3. Actions → Deploy production → Run workflow
4. Actions → Recompute latest evidence → Run workflow
5. Lire la page Preuves, couverture et funnel
```

Le recalcul V3.9 consomme **zéro crédit fournisseur**. Il télécharge le dernier artefact `historical-sample-evidence-*`, recalcule les dénominateurs, publie le rapport puis redéploie le dashboard.

## Workflows principaux

```text
Deploy production
Verify production
Run historical sample
Recompute latest evidence
Rebuild fresh football model
Backup and verify database
Rollback model release
Generate handoff package
```

## Configuration GitHub

### Secrets

```text
RAILWAY_TOKEN
RAILWAY_PROJECT_ID
APP_PASSWORD
THE_ODDS_API_KEY          uniquement pour une nouvelle collecte
DATABASE_URL              sauvegardes et autres opérations PostgreSQL
BACKUP_ENCRYPTION_PASSPHRASE
```

### Variables

```text
APP_PUBLIC_URL
RAILWAY_ENVIRONMENT
RAILWAY_WEB_SERVICE
RAILWAY_CRON_SERVICE_ID
```

`Recompute latest evidence` n’utilise pas `THE_ODDS_API_KEY` et ne lit pas `DATABASE_URL`.

## Lecture des résultats

- **Intégrité technique** : horodatage, doublons, fin du backfill et plafond de crédits.
- **Couverture fournisseur** : réponses reçues / cibles exécutées.
- **Matching** : événements rapprochés de façon fiable / événements retournés.
- **Consensus** : cibles possédant au moins deux marchés bookmaker complets.
- **Winamax** : cibles possédant un marché Winamax complet.
- **Preuve statistique** : taille d’échantillon indépendante de la qualité technique.

Une couverture Winamax faible ne bloque plus automatiquement un benchmark contre le consensus.

## Limites

- aucune rentabilité démontrée ;
- aucune recommandation de mise ;
- aucun pari automatique ;
- aucune promotion automatique de modèle ;
- un petit lot reste une validation technique, même lorsque les portes qualité passent.
