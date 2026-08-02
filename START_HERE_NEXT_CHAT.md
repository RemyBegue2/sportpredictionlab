# START HERE — Sports Prediction Lab V3.6

## État confirmé

- Version applicative : **3.6.0**
- Railway : service web, `shadow-cron`, PostgreSQL, worker historique manuel
- Modèle football frais existant conservé depuis la V3.4/V3.5
- Déploiement et intégrité déjà traçables via `/api/release`
- Décision champion–challenger disponible via `/api/model-decision`
- Promotion et paris automatiques désactivés

## Travail V3.6 livré

- champion, Winamax, consensus et blend 50/50 enregistrés séparément en shadow ;
- benchmark multi-contenders ;
- portes de promotion déterministes ;
- backfill historique immuable et limité par défaut à 30 événements ;
- approbation exacte du plan pour un backfill complet ;
- handoff enrichi.

## Vérité statistique

Aucun benchmark historique réel n’a encore été exécuté dans le paquet. Ne pas annoncer de rentabilité.

## Prochaine action prioritaire

Créer puis examiner un plan historique de 30 événements EPL à T−1 h, avec un plafond de crédits explicite. Exécuter le benchmark `model` contre `blend50`, Winamax et consensus seulement après validation de la collecte.

## Fichiers à lire

1. `handoff/HANDOFF_CURRENT.md`
2. `handoff/HANDOFF_CURRENT.json`
3. `handoff/NEXT_ACTIONS.md`
4. `AUDIT_MULTI_ROLES_V3_6.md`
5. `RESULTATS_V3_6.md`
