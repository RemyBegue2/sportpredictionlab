# Changelog

## V4.9.0 — Controlled Model Decision & Live Validation

- entraîne exactement deux challengers football bornés : Poisson régularisé et hybride Poisson/Elo ;
- utilise une zone de développement antérieure au holdout déjà consulté ;
- conserve le champion lorsque les sous-groupes protégés ou la calibration se dégradent ;
- ouvre une génération de holdout future nécessitant 30 nouvelles dates avant toute promotion ;
- ajoute un import tennis incrémental avec déduplication, corrections explicites et version précédente conservée ;
- ajoute un endpoint et un workflow de décision contrôlée à zéro crédit ;
- sépare la validation publique longue session en scénarios simple et expert ;
- conserve exactement trois onglets et traduit les états techniques en décisions lisibles ;
- maintient zéro crédit d’entraînement, zéro promotion automatique et zéro pari réel.

## V4.8.0 — Evidence Acceleration & Production Hardening

- ajoute un pipeline d’import tennis avec normalisation, déduplication, quarantaine et lineage temporelle ;
- versionne les datasets et les générations de holdout avec identifiants et SHA-256 déterministes ;
- explique le `hold` football par outcome, saison, forme de marché, historique d’équipe et repos ;
- limite explicitement le prochain tour football à deux challengers probabilistes ;
- ajoute Alembic avec adoption contrôlée du schéma existant et migration des nouvelles tables ;
- fige les actions GitHub par SHA complets vérifiés ;
- ajoute un workflow public de stabilité longue session avec contrôle du DOM et des requêtes ;
- conserve exactement trois onglets simples et ajoute une synthèse d’action par écran ;
- maintient zéro crédit d’entraînement, zéro promotion automatique et zéro pari réel.

## V4.7.0 — Stable Challenger Cockpit

- ajoute une Challenger Factory football/tennis à zéro crédit avec datasets hashés, splits chronologiques et paramètres portables ;
- entraîne réellement le challenger football et conserve le champion lorsque le holdout ne passe pas les portes ;
- refuse d’inventer une preuve tennis lorsque l’archive multi-surface est insuffisante ;
- déduplique les GET concurrents, ajoute des timeouts, annule les requêtes à la fermeture et rend le mode expert réessayable ;
- plafonne les listes simples à huit cartes et réduit l’apprentissage à quatre indicateurs ;
- renforce le smoke navigateur avec une navigation répétée de longue session ;
- conserve zéro promotion automatique, zéro pari réel et zéro crédit d’entraînement.

## V4.6.0 — Robust Calibration & Compact Cockpit

- calibration football et tennis évaluée sur holdout chronologique ;
- registre borné d’expériences et audit de lineage temporelle ;
- Feature Lab à zéro crédit fournisseur ;
- interface simple transformée en cockpit à trois onglets, un seul écran visible à la fois ;
- mode expert conservé et chargé à la demande ;
- promotion automatique toujours interdite.


## V4.5.0 — Automated Shadow Learning & Simple UI

- makes the simple daily view the default and defers expert endpoints until the operator opens expert mode ;
- groups the interface into Today, Signals and Learning, with bankroll and training details collapsed by default ;
- adds an auditable paper-bankroll path without creating a real staking instruction ;
- adds a shared local-day credit ledger across capture and settlement ;
- skips paid football capture on automated empty-fixture days ;
- adds bounded scheduled capture, settlement and weekly zero-credit challenger training ;
- adds strict champion–challenger promotion gates for total sample, per-sport sample, holdout signals, drawdown and chronological stability ;
- creates stable `RCH-*` challenger identifiers and a manual-only promotion endpoint/workflow ;
- keeps historical evidence disabled and preserves no-bet, no-stake and no-automatic-promotion invariants ;
- adds regression coverage for the simple UI, lazy expert loading, daily budget, no-op settlement and manual promotion.

## V4.4.0 — Dual-Sport ROI Lab

- adds one persisted football-and-tennis research view for today’s matches, probabilities, shadow signals and simulated bankrolls ;
- adds manual credit-capped workflows to capture live markets and settle football/tennis results ;
- requires shadow recording before any paid daily snapshot can be captured ;
- adds flat 1 %, flat 2 % and quarter-Kelly-capped bankroll simulations for fictitious bankrolls 100, 500 and 1,000 ;
- tunes a bounded 144-policy grid on chronological development folds with instability, downside and drawdown penalties ;
- trains a portable logistic signal-quality meta-model on chronological train/validation/holdout splits ;
- counts one decision per event rather than treating mutually exclusive outcomes as independent samples ;
- requires at least 30 settled events for a sport before the meta-model may rehabilitate a base-model abstention ;
- keeps the dashboard read-only with respect to paid provider calls ;
- strengthens the Chromium smoke test to require the ROI lab to render ;
- preserves no real stake, no automatic bet and no profitability-claim invariants.

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
