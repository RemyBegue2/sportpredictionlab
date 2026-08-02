# START HERE — Sports Prediction Lab V3.7

## État de référence

- Version : **3.7.0 Cloud Control Center**
- Hébergement : Railway
- Automatisation : GitHub Actions
- Exploitation locale : **aucun Python requis**
- Modèle football : champion/challengers en shadow avec preuves V3.6
- Paris automatiques : désactivés
- Promotion automatique : désactivée

## Nouveautés V3.7

- `/api/control-center` ;
- page Pilotage ;
- déploiement vérifié version/commit/hash ;
- smoke test Chromium authentifié ;
- benchmark historique plafonné depuis GitHub ;
- sauvegarde restaurée automatiquement avant publication ;
- rollback depuis un commit Git connu, protégé par confirmation ;
- ZIP de reprise généré par GitHub Actions.

## Prochaine action

Ouvrir **Actions → Historical validation sample → plan_only**, choisir une courte période EPL et télécharger l’artefact. Ne passer à `execute_sample` qu’après lecture des plafonds.

## Vérité statistique

Aucune preuve suffisante ne permet encore d’affirmer que le modèle bat Winamax ou le consensus.

## Fichiers prioritaires

1. `handoff/HANDOFF_CURRENT.md`
2. `handoff/HANDOFF_CURRENT.json`
3. `handoff/NEXT_ACTIONS.md`
4. `AUDIT_MULTI_ROLES_V3_7.md`
5. `RESULTATS_V3_7.md`
