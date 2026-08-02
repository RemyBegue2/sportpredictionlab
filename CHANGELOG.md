# Changelog

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
