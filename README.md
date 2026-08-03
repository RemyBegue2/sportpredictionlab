# Sports Prediction Lab V4.4 — Dual-Sport ROI Lab

La V4.4 présente les matchs de football et de tennis du jour dans une vue unique, ajoute des signaux de marché strictement expérimentaux, simule plusieurs bankrolls fictives et entraîne une politique de sélection avec validation chronologique.

## Parcours simple

```text
Matchs du jour
→ probabilités football / tennis
→ cotes live sous plafond facultatif
→ signal shadow ou abstention expliquée
→ règlement du résultat
→ bankrolls simulées
→ politique ROI et méta-modèle sur holdout
```

## Mode sûr par défaut

```text
DAILY_ODDS_ENABLED=false
DAILY_ODDS_MAX_CREDITS=0
SHADOW_MODE_ENABLED=false
HISTORICAL_EVIDENCE_ENABLED=false
```

Le calendrier et les probabilités modèle seules restent disponibles sans crédit. Une capture live payante exige un plafond, le mode shadow et une confirmation humaine.

## Endpoints

```text
/api/daily/slate
/api/research-lab
/api/research-lab/refresh
/api/research-lab/settle
/api/research-lab/optimise
/api/model-diagnostics
/api/credit-firewall
/api/release
/api/ready
```

## Workflows

```text
Refresh daily product
Capture daily football and tennis research
Settle daily football and tennis research
Optimise simulated ROI policy
Deploy production
Verify production
```

## Garanties

- aucun appel fournisseur déclenché par l'ouverture du dashboard ;
- aucune mise réelle ou personnalisée ;
- aucun placement automatique ;
- politiques choisies sur blocs chronologiques et holdout ;
- une seule observation par événement pour le méta-modèle ;
- tennis normalement en abstention tant qu'une preuve spécifique au sport est insuffisante ;
- aucun ROI simulé présenté comme une rentabilité future.

Documents V4.4 :

- `UPGRADE_V4_4.md`
- `AUDIT_MULTI_ROLES_V4_4.md`
- `RESULTATS_V4_4.md`
- `KNOWN_ISSUES_AND_GATES_V4_4.md`
- `OPERATIONS_RUNBOOK_V4_4.md`
- `VALIDATION_V4_4.json`

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
