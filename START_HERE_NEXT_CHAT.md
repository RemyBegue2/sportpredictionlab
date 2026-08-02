# START HERE — Sports Prediction Lab V3.5

Ce fichier est le point d’entrée canonique d’une nouvelle conversation.

## État attendu après déploiement

- application privée Railway ;
- service web `sportpredictionlab` ;
- service `shadow-cron` ;
- PostgreSQL partagé ;
- The Odds API configurée côté serveur ;
- API `3.5.0` ;
- preuve publique `/api/release` ;
- état complet privé `/api/system/status` ;
- modèles et releases enregistrés en base ;
- historique shadow inchangé.

## À ne jamais supposer

- qu’un workflow vert a été déployé ;
- que le modèle bat Winamax ;
- que le modèle frais est `active` ;
- que le tennis est calibré ;
- qu’une restauration PostgreSQL a été testée sans rapport explicite.

## Fichiers à lire dans l’ordre

1. `handoff/HANDOFF_CURRENT.md`
2. `handoff/HANDOFF_CURRENT.json`
3. `artifacts/release_manifest.json`
4. `artifacts/fresh_rebuild_report.json`
5. dernier log Railway ou GitHub Actions joint par l’utilisateur

## Vérifications prioritaires

1. comparer `/api/release.version` avec le commit attendu ;
2. comparer `source_commit` au dernier commit déployé ;
3. vérifier `artifact_integrity_ok` ;
4. identifier le modèle football actif et son cutoff ;
5. lire les métriques shadow par modèle et horizon ;
6. distinguer les faits vérifiés des inférences.

## Règles permanentes

- pré-match uniquement ;
- aucune connexion au compte Winamax ;
- aucun pari automatique ;
- aucune taille de mise ;
- aucun historique réécrit silencieusement ;
- une shortlist vide est valide ;
- aucune rentabilité annoncée sans preuve hors échantillon.
