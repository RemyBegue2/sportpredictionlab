# Mise à niveau V4.0 → V4.1

## Objet

La V4.1 ne change pas le périmètre sportif. Elle corrige l’intégrité de la décision, la reprise après interruption et les contrôles de production avant toute montée vers les stages 100, 300 ou 1 000.

## Installation sans Python local

1. Remplacer le contenu du dépôt GitHub par celui de l’archive V4.1, en conservant les secrets GitHub, les variables Railway, la base PostgreSQL et les artefacts modèles actifs.
2. Créer une branche de mise à niveau et une pull request.
3. Vérifier que les tests GitHub Actions réussissent.
4. Fusionner après revue humaine.
5. Lancer **Deploy production**.
6. Vérifier que `/api/ready` répond avec un statut prêt et que `/api/release` annonce `4.1.1` avec le commit attendu.
7. Lancer **Run evidence campaign → dry_run → stage 30** avant tout appel fournisseur.

## Changements incompatibles à connaître

- `continue_current_stage` ne peut reprendre que la campagne exacte déjà créée. Il ne permet plus de choisir arbitrairement un stage supérieur.
- Un consensus exige au moins deux bookmakers indépendants après exclusion de Winamax.
- Les collisions de matching deviennent bloquantes.
- Une campagne incomplète produit `HOLD`; une corruption temporelle, un doublon, une collision ou un dépassement de plafond produit `FAIL`.
- Le nombre de stage repose sur les événements uniques prêts pour la baseline, pas sur le nombre brut de requêtes ou de snapshots.
- Un appel de découverte dont la facturation est incertaine n’est pas rejoué sans l’option explicite `retry_uncertain_discovery`.
- Railway et Docker utilisent `/api/ready` comme sonde de disponibilité.

## Variables et secrets

Secrets nécessaires selon l’opération :

- `THE_ODDS_API_KEY`
- `RAILWAY_TOKEN`
- `RAILWAY_PROJECT_ID`
- `APP_PASSWORD`
- `DATABASE_URL` dans Railway pour l’application
- `DATABASE_PUBLIC_URL` dans GitHub pour le workflow de sauvegarde
- `BACKUP_ENCRYPTION_PASSPHRASE`

Variables principales :

- `APP_PUBLIC_URL`
- `RAILWAY_ENVIRONMENT`
- `RAILWAY_WEB_SERVICE`
- `RAILWAY_CRON_SERVICE`

## Validation minimale après déploiement

- version `4.1.1` confirmée ;
- commit déployé confirmé ;
- modèle et hash confirmés ;
- `/api/ready` vert ;
- `dry_run` sans crédit réussi ;
- checkpoint partiel restaurable ;
- rapport V4.1 affichant un verdict unique ;
- aucune progression au stage 100 sans `PASS` réel du stage 30.

## Retour arrière

Utiliser le workflow **Rollback production** avec sa confirmation explicite. Le verrou commun `production-change` empêche les autres workflows de modification de production de s’exécuter en parallèle.

## Hotfix V4.1.1

Pour le backup GitHub, copier la valeur **résolue** de l’URL publique PostgreSQL Railway dans le secret `DATABASE_PUBLIC_URL`. Ne pas copier une référence `${{ ... }}`, une URL `.railway.internal` ou une URL dont le port est vide.
