# Audit multi-rôles V3.6 — Evidence Engine & Champion–Challenger

## Verdict exécutif

**GO technique** pour déployer V3.6 et lancer un petit lot historique contrôlé.

**NO-GO statistique** pour annoncer que le modèle bat Winamax, recommander une mise ou promouvoir automatiquement un challenger. Aucun benchmark historique réel n’a été exécuté dans cette livraison.

## 1. Product Owner

**Retour :** la V3.5 prouvait ce qui était déployé, mais ne donnait pas une décision lisible sur la valeur du modèle.

**Décision intégrée :** nouvelle page « Décision modèle » et endpoint `/api/model-decision`. Le verdict est `not_evaluable`, `continue_shadow`, `no_go` ou `promotion_review`, avec une prochaine action explicite.

## 2. Statisticien

**Retour :** un ROI isolé et une seule métrique globale sont trop instables.

**Décision intégrée :** log-loss, Brier, RPS, ECE, comparaison appariée au consensus, bootstrap par blocs, stabilité par fold et CLV. Les seuils minimaux sont 1 000 observations historiques et 200 observations live shadow avant une revue de promotion.

## 3. Auditeur anti-fuite

**Retour :** chaque contender doit être évalué sur les mêmes lignes et aucune cote future ne doit être utilisée.

**Décision intégrée :** tous les contenders passent par le même `run_market_benchmark`, les mêmes folds chronologiques et le même audit temporel. Les lignes invalides sont rejetées, jamais réparées silencieusement.

## 4. ML Engineer

**Retour :** un champion unique masque le coût d’opportunité des alternatives.

**Décision intégrée :** architecture multi-prefixes (`model`, `blend50`, futurs Elo/Poisson), leaderboard descriptif et portes de promotion. La promotion reste humaine.

## 5. Quant marchés

**Retour :** le consensus et Winamax doivent être des baselines, pas seulement des cotes affichées.

**Décision intégrée :** Winamax, consensus dévigé et blend 50/50 sont enregistrés comme flux shadow immuables distincts. Le blend est également disponible dans le benchmark historique.

## 6. Data Engineer

**Retour :** le backfill doit être reprenable, dédupliqué et vérifiable.

**Décision intégrée :** `plan_id`, hashes des requêtes et cibles, checkpoints atomiques, chunks hashés et reprise par numéro de requête.

## 7. FinOps API

**Retour :** un backfill complet peut consommer des crédits sans contrôle.

**Décision intégrée :** validation limitée par défaut à 30 événements, plafond immuable, dry-run et approbation exacte du `plan_id` pour un plan complet.

## 8. SRE / DevOps

**Retour :** un workflow vert ne suffit pas et un worker coûteux ne doit jamais redémarrer en boucle.

**Décision intégrée :** vérification post-déploiement de `/api/release` et `/api/model-decision`, worker Railway avec `restartPolicyType = NEVER` et exécution manuelle.

## 9. QA

**Retour :** les contrats UI/API et les règles de décision doivent être testés.

**Décision intégrée :** tests sur le leaderboard, les portes de promotion, l’intégrité du plan, l’endpoint, la persistance et les identifiants frontend. Résultat : 99 tests réussis.

## 10. Sécurité

**Retour :** aucun secret ne doit entrer dans les rapports ou le handoff.

**Décision intégrée :** les exports restent sans variable d’environnement. Le scan local n’a trouvé aucun secret réel ; une chaîne de test a été classée faux positif.

## 11. Responsable jeu responsable

**Retour :** une preuve préliminaire ne doit pas devenir une incitation à parier.

**Décision intégrée :** `automatic_promotion=false`, `profitability_claim=false`, aucune taille de mise, aucune connexion au compte et aucune exécution automatique.

## 12. Mainteneur / Reprise de conversation

**Retour :** le prochain assistant doit connaître l’état exact sans relire tout l’historique.

**Décision intégrée :** export de six fichiers de continuité : état courant, benchmark, model card et prochaines actions.

## Risques résiduels

1. Le benchmark réel reste à exécuter avec un quota connu.
2. Le matching d’événements doit être contrôlé sur les 30 premiers matchs.
3. Le blend 50/50 est un challenger simple, pas un poids optimisé garanti.
4. Les challengers Elo/Poisson dédiés restent une extension, pas une condition de sortie V3.6.
5. La restauration PostgreSQL managée doit encore être testée sur Railway.

## Décision finale consolidée

- Déploiement de V3.6 : **GO**.
- Lot historique de 30 événements : **GO sous plafond de crédits**.
- Backfill complet : **GO conditionnel après examen du premier lot**.
- Promotion automatique : **INTERDITE**.
- Communication de rentabilité : **INTERDITE à ce stade**.
