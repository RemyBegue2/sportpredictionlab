# Sports Prediction Lab V4.3 — Daily Product Recovery & Credit Firewall

La V4.3 remet le produit quotidien au premier plan. Le calendrier, les probabilités du modèle, son état de santé et les raisons d’absence de shortlist sont disponibles sans appel payant à The Odds API.

## Fonctionnement par défaut

```text
Calendrier gratuit mis en cache
→ normalisation des équipes
→ prédictions 1N2 du modèle
→ stockage idempotent PostgreSQL
→ affichage quotidien et matchs à venir
```

Les cotes et les campagnes historiques sont suspendues par défaut :

```text
DAILY_ODDS_ENABLED=false
DAILY_ODDS_MAX_CREDITS=0
HISTORICAL_EVIDENCE_ENABLED=false
SHADOW_MODE_ENABLED=false
```

## Endpoints principaux

```text
/api/daily/slate
/api/model-diagnostics
/api/credit-firewall
/api/release
/api/ready
```

## Workflows principaux

```text
Deploy production
Refresh daily product
Verify production
Generate handoff package
```

Les workflows evidence restent disponibles pour audit et recomputation, mais les modes payants exigent une réactivation explicite du pare-feu et leur confirmation humaine.

## Garanties

- zéro crédit pour le calendrier et les probabilités modèle seules ;
- aucune shortlist forcée ;
- aucune recommandation de mise ;
- aucun placement automatique ;
- aucune promotion automatique ;
- panne des sources de calendrier affichée explicitement sans rendre l’application indisponible ;
- cotes facultatives, désactivées et plafonnées par défaut.

Documents V4.3 :

- `UPGRADE_V4_3.md`
- `AUDIT_MULTI_ROLES_V4_3.md`
- `RESULTATS_V4_3.md`
- `KNOWN_ISSUES_AND_GATES_V4_3.md`
- `OPERATIONS_RUNBOOK_V4_3.md`
- `VALIDATION_V4_3.json`

---
# Sports Prediction Lab V3.7 — Cloud Control Center

Application privée de recherche football/tennis avec FastAPI, PostgreSQL, The Odds API, shadow mode pré-match et moteur champion–challenger.

La V3.7 rend l’exploitation **100 % navigateur** : GitHub Actions exécute les scripts et Railway héberge les services. Aucun Python n’est requis sur l’ordinateur de l’utilisateur.

## Nouveautés V3.7

- page **Centre de contrôle** et endpoint privé `/api/control-center` ;
- statuts déterministes : opérationnel, en attente, action nécessaire ou bloqué ;
- prochaines actions reliées au workflow GitHub exact à lancer ;
- workflow **Deploy production** : tests, déploiement Railway, preuve `/api/release`, puis test Chromium authentifié ;
- workflow **Verify production** sans redéploiement ;
- workflows **Estimate historical sample** et **Run historical sample** avec estimation zéro crédit puis exécution plafonnée à 30 événements ;
- workflow **Backup and verify database** avec restauration de contrôle ;
- workflow **Rollback model release** restaurant les artefacts depuis un commit Git connu et protégé par confirmation explicite ;
- workflow **Generate handoff package** produisant un ZIP directement joignable dans une nouvelle conversation ;
- commit embarqué dans le manifeste de release, même lors d’un déploiement `railway up` sans dossier `.git` ;
- résumés lisibles dans `GITHUB_STEP_SUMMARY` pour chaque opération.

## Opérations courantes

Dans GitHub :

```text
Actions
→ choisir le workflow
→ Run workflow
→ remplir les paramètres
→ lire le résumé du run
```

Workflows disponibles :

```text
Deploy production
Verify production
Rebuild fresh football model
Estimate historical sample puis Run historical sample
Backup and verify database
Rollback model release
Generate handoff package
```

## Configuration GitHub nécessaire

### Secrets

```text
RAILWAY_TOKEN
RAILWAY_PROJECT_ID
APP_PASSWORD              test navigateur privé
THE_ODDS_API_KEY          collecte historique
DATABASE_URL              connexion PostgreSQL du runtime Railway
DATABASE_PUBLIC_URL       secret GitHub pour sauvegarde PostgreSQL externe
BACKUP_ENCRYPTION_PASSPHRASE  chiffrement de la sauvegarde (20 caractères minimum)
```

### Variables

```text
APP_PUBLIC_URL
RAILWAY_ENVIRONMENT       production par défaut
RAILWAY_WEB_SERVICE       sportpredictionlab par défaut
RAILWAY_CRON_SERVICE      shadow-cron par défaut
```

Les workflows expliquent précisément la configuration manquante lorsqu’une opération est bloquée.

## Déploiement après l’upgrade

1. Remplacer les fichiers du dépôt par le contenu de l’archive V3.7, sans écraser les modèles ni les données actives.
2. Créer un commit dans GitHub.
3. Ouvrir **Actions → Deploy production → Run workflow**.
4. Garder `deploy_web`, `deploy_cron` et `verify_browser` activés.
5. Le run est considéré réussi seulement après vérification de la version, du commit, du hash du modèle et, par défaut, de l’interface privée dans Chromium.

## Premier benchmark historique

1. Ouvrir **Actions → Estimate historical sample**.
2. Choisir `plan_only` : aucun crédit API n’est consommé.
3. Télécharger et lire l’artefact de planification.
4. Relancer avec `execute_sample`, un maximum de 30 événements et la confirmation `EXECUTE_SAMPLE`.
5. Ne jamais lancer une période ou un plafond plus large avant examen du premier lot.

## Reprise dans une autre conversation

```text
Actions
→ Generate handoff package
→ Run workflow
→ télécharger sports-prediction-handoff-v3.8
→ joindre le ZIP dans la nouvelle conversation
```

Le ZIP exclut les variables d’environnement, clés, tokens, mots de passe, cookies et URL de base de données.

## Limites inchangées

- aucune rentabilité démontrée ;
- aucune promotion automatique de challenger ;
- aucune taille de mise ;
- aucune connexion à un compte Winamax ;
- aucun pari automatique ;
- le tennis reste expérimental et non calibré.

## V3.8 — Cloud Evidence Run

La V3.8 ajoute une chaîne entièrement cloud pour produire les premières preuves historiques sans Python local :

```text
GitHub Actions → Estimate historical sample
→ REQ-... sans appel fournisseur
→ Run historical sample avec plafonds identiques
→ collecte et checkpoints PostgreSQL
→ contrôle temporel et qualité
→ benchmark modèle / Winamax / consensus lorsque possible
→ rapport publié
→ dashboard Railway redéployé
```

Endpoints :

```text
/api/evidence
/api/benchmark/summary
/api/model-decision
/api/release
```

La V3.8 ne place aucun pari et ne promeut aucun modèle automatiquement.
