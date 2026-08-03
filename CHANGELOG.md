# Changelog

## V4.3.0 — Daily Product Recovery & Credit Firewall

- adds zero-credit daily fixture discovery with cached ESPN and Football-Data fallback sources ;
- generates idempotent model-only Premier League predictions without requiring market odds ;
- adds explicit model diagnostics separating research usability from market-shortlist readiness ;
- adds `/api/daily/slate`, `/api/model-diagnostics` and `/api/credit-firewall` ;
- replaces the paid shadow cron with a six-hour zero-credit daily-product refresh ;
- disables daily paid odds and historical evidence by default ;
- guards paid historical workflows behind `HISTORICAL_EVIDENCE_ENABLED=true` and existing human confirmations ;
- updates the dashboard with today’s probabilities, upcoming matches, credit usage and abstention reasons ;
- preserves no-bet, no-stake and no-automatic-promotion invariants.
- expands the default upcoming horizon to 31 days so off-season pages can show the next league round ;
- normalizes current/promoted club aliases and keeps unsupported clubs as explicit cold-start predictions shrunk toward league priors ;
- prevents cold-start predictions from becoming market candidates ;
- adds source-failure backoff, streamed 5 MB response limits and stable cross-provider fixture identifiers ;
- avoids calling paid-odds endpoints from the UI while the credit firewall is closed ;
- adds a PostgreSQL transaction lock for concurrent idempotent daily refreshes.

## V4.2.1 — Frontend preflight rendering hotfix

- Déplace le formateur de pourcentage `pct` au niveau partagé afin que `renderPreflight` puisse l'utiliser.
- Ajoute un test Node exécutant réellement le rendu du préflight.
- Renforce le smoke test Chromium : le panneau préflight doit être rendu et tout message `Interface partiellement chargée` fait échouer la vérification.
- Change la version des assets pour invalider le cache navigateur.

## V4.2.0 — Coverage-Aware Evidence Planning

- adds a resumable, credit-capped `Estimate evidence coverage` workflow before any full historical backfill ;
- classifies proposed campaigns as `VIABLE`, `RISKY` or `NOT_VIABLE` from bookmaker availability, budget and uncertainty ;
- blocks paid evidence campaigns unless an exact immutable `VIABLE` preflight matches the baseline, stage, budget and app version ;
- oversamples candidate events so the stage target represents benchmark-ready observations rather than merely requested matches ;
- requires at least two independent complete bookmakers for a consensus preflight ;
- keeps Pinnacle as a separate provider-availability experiment and never substitutes it silently for Winamax/consensus ;
- hashes the probe set, odds evidence and candidate event pool, then materializes the exact embedded candidate plan used by the campaign ;
- adds `/api/coverage-preflight` and a dashboard summary before paid execution ;
- adds V4.2 regression coverage for empty provider responses, resumability, uncertain billing, plan tampering, budget rejection and the real low-coverage scenario.

## V4.1.3 — Railway CLI detached deployment hotfix

- switches every GitHub Actions `railway up` invocation from CI log streaming to detached queue mode ;
- prevents a successful Railway upload/deployment from being reported as failed only because build-log streaming is temporarily unavailable ;
- keeps exact post-deployment validation of version, commit, model hash and readiness for every web deployment ;
- adds regression tests preventing `railway up --ci` from returning to production workflows.

## V4.1.2 — Readiness recovery & test isolation hotfix

- Fixed deployment pipeline failure caused by leaked global startup state between tests.
- `/api/ready` now clears stale startup diagnostics after successful live checks.
- Added regression coverage for transient startup recovery.


## V4.1.1 — Railway readiness & backup connectivity hotfix

- rend `/api/ready` accessible aux sondes Railway/Docker même lorsque l’authentification applicative est activée ;
- conserve toutes les routes métier en accès privé ;
- préfère le secret GitHub `DATABASE_PUBLIC_URL` pour les sauvegardes exécutées hors du réseau privé Railway ;
- normalise les URL PostgreSQL copiées avec des guillemets ;
- refuse les ports vides/non numériques et les hôtes `.railway.internal` depuis GitHub Actions avec un message sans identifiants ;
- transforme l’ancien traceback SQLAlchemy en erreur de configuration actionnable ;
- ajoute 6 tests de régression, portant la suite à 161 tests réussis par lots.

## V4.1.0 — Decision Integrity & Resumable Operations

- verdict canonique `PASS/HOLD/FAIL` partagé par le rapport, la porte de scale-up et le dashboard ;
- progression calculée côté serveur et impossibilité de transformer `continue_current_stage` en passage au stage supérieur ;
- stage fondé sur les événements uniques réellement prêts pour la baseline sélectionnée ;
- matching bijectif avec mise en quarantaine des collisions ;
- consensus composé d’au moins deux bookmakers indépendants après exclusion de Winamax ;
- contrôles et compteurs spécifiques à la baseline `consensus` ou `winamax` ;
- checkpoint atomique après chaque appel de découverte facturable et reprise depuis un checkpoint partiel ;
- appels à facturation incertaine non rejoués sans autorisation explicite ;
- comptabilité séparée des crédits de découverte, de snapshots et du total ;
- readiness Railway/Docker sur `/api/ready` ;
- verrou commun `production-change` pour les workflows modifiant la production ;
- source de version centralisée ;
- 155 tests réussis et couverture cœur de 83 %.

## V4.0.0

- workflow unique `Run evidence campaign` ;
- stages 30/100/300/1000 ;
- plan zero crédit sans identifiant manuel ;
- porte de scale-up data/statistique ;
- checkpoint GitHub compatible et reprise contrôlée ;
- rapport et endpoint `/api/evidence-campaign` ;
- interface de campagne ;
- version de production 4.0.0 ;
- 145 tests et couverture 83 %.

## 3.5.0

- preuve publique `/api/release` ;
- état consolidé `/api/system/status` ;
- registre de releases et transitions de modèles ;
- unicité du modèle actif par sport ;
- métriques shadow par modèle/version/horizon ;
- manifeste de release sans secret ;
- snapshot et rollback d’artefacts ;
- export de handoff pour une nouvelle conversation ;
- backup/restore applicatif portable ;
- frontend chargé par sections indépendantes ;
- vérification post-déploiement optionnelle dans GitHub Actions ;
- 91 tests réussis.

## 3.4.3

- Corrige le crash frontend causé par le sélecteur inexistant `#benchmarkState`.
- Ajoute un test de contrat entre les sélecteurs JavaScript et les identifiants HTML.
- Ajoute un cache-busting `app.js?v=3.4.3`.
- Déploie explicitement le service web et `shadow-cron` via Railway CLI après une reconstruction réussie.

## 3.4.1

- Corrige le parsing des colonnes de dates mélangeant `YYYY-MM-DD` et timestamps ISO complets après reconstruction fraîche.
- Ajoute une régression couvrant les formats temporels mixtes utilisés par les endpoints football.
- Porte la version API et le cache frontend à 3.4.1.

## 3.4.0

- Ajout des diagnostics détaillés de cycles shadow.
- Ajout du verrou anti-chevauchement PostgreSQL.
- Ajout des statuts de cycle explicites.
- Ajout du pipeline multi-saisons Premier League.
- Ajout des règles de promotion et du candidat séparé.
- Ajout du workflow GitHub Actions de reconstruction.
- Conservation des artefacts préconstruits dans Docker.
- Version API et frontend portée à 3.4.0.

## 3.6.0 — Evidence Engine & Champion–Challenger

- ajout de `/api/model-decision` et de la page de décision ;
- collecte shadow du champion, de Winamax, du consensus et du blend 50/50 ;
- benchmark multi-contenders ;
- plan de backfill immuable, validation 30 événements et approbation exacte des plans complets ;
- décisions de modèle persistées ;
- handoff enrichi ;
- 99 tests, 85 % de couverture.

## 3.7.0 — Cloud Control Center

- exploitation GitHub Actions + Railway sans Python local ;
- endpoint et page `/api/control-center` ;
- workflows de déploiement, vérification, handoff, historique, sauvegarde et rollback ;
- preuve du commit embarqué pour les déploiements CLI Railway ;
- test Chromium authentifié ;
- résumés d’actions lisibles ;
- pack de continuité téléchargeable.

## 3.8.0 — Cloud Evidence Run & Data Quality Gate

- estimation historique sans appel fournisseur ;
- identifiant de demande immuable `REQ-...` ;
- exécution plafonnée et explicitement confirmée ;
- audit temporel et quarantaine ;
- couverture événements et Winamax ;
- tentative de benchmark modèle/Winamax/consensus ;
- endpoint `/api/evidence` ;
- dashboard Preuves et benchmark ;
- pack de reprise V3.8 ;
- test navigateur étendu au dashboard de preuve.
