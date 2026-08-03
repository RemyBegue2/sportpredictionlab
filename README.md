# Sports Prediction Lab V4.1 — Decision Integrity & Resumable Operations

La V4.1 durcit la campagne de preuve cloud avant toute montée en volume. Elle impose un verdict canonique `PASS/HOLD/FAIL`, empêche le contournement des stages, compte uniquement les événements uniques réellement prêts pour le benchmark, exige deux bookmakers indépendants pour le consensus et reprend la découverte après interruption sans perdre silencieusement les crédits déjà consommés.

Le workflow principal reste `Run evidence campaign`, piloté depuis GitHub Actions et Railway, sans Python local. Les opérations responsables restent inchangées : aucun pari automatique, aucune recommandation de mise et aucune promotion automatique de modèle.

Documents V4.1 :

- `UPGRADE_V4_1.md`
- `AUDIT_MULTI_ROLES_V4_1.md`
- `RESULTATS_V4_1.md`
- `KNOWN_ISSUES_AND_GATES_V4_1.md`
- `OPERATIONS_RUNBOOK_V4_1.md`
- `VALIDATION_V4_1.json`

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
DATABASE_URL              benchmark et sauvegarde PostgreSQL
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
