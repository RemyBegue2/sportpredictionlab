# Audit multi-rôles — Sports Prediction Lab V4.2.0

## Verdict consolidé

- **Code V4.2.0 : GO pour revue et déploiement contrôlé.**
- **Préflight réel : GO avec petit plafond et approbation humaine.**
- **Campagne payante : uniquement après verdict `VIABLE`.**
- **Stage 100 : NO-GO tant que le stage 30 réel n'est pas `PASS`.**

## Product Owner

Le produit résout maintenant le coût d'apprentissage tardif observé en V4.1. La question principale est posée avant le backfill complet : la baseline demandée peut-elle vraisemblablement fournir le nombre d'observations benchmark-ready sous le budget disponible ? Le dashboard expose le verdict, la couverture, le nombre recommandé et le coût du préflight.

Retour intégré : un stage de 30 signifie 30 observations évaluables, pas 30 matchs demandés. Le planificateur sur-échantillonne donc automatiquement.

## Data Engineer

Le préflight échantillonne les événements de manière déterministe et répartie dans le temps, sans consulter les scores, résultats ou métriques du modèle. Il exige trois issues h2h complètes par bookmaker et deux bookmakers indépendants pour le consensus.

Les sondes, la preuve de cotes et le pool candidat sont hashés. Le planificateur de campagne rematérialise le plan candidat intégré au rapport, ce qui élimine la divergence entre un rapport valide et un fichier candidat séparé.

## Statisticien / Quant

Le calcul de capacité combine couverture observée et seuil minimal de matching afin d'estimer le nombre de matchs à sélectionner. Une couverture basse dont la borne haute Wilson reste sous 70 % est refusée. Une couverture prometteuse mais incertaine produit `RISKY`, jamais `VIABLE`.

Limite importante : le Wilson est utilisé comme diagnostic conservateur sur un échantillon déterministe. Il ne doit pas être présenté comme un intervalle de confiance de population obtenu par tirage aléatoire. Cette limite est maintenant incluse dans le rapport.

Pinnacle reste une expérience séparée. Il ne peut pas valider silencieusement une campagne Winamax/consensus.

## FinOps

Le budget de préflight inclut découverte et sondes. Le budget futur de campagne réserve son propre coût de découverte, même si le préflight a bénéficié du cache. La capacité de snapshots est calculée après cette réservation.

Chaque appel est précédé d'une réservation au coût maximal. Une interruption marque l'appel comme potentiellement facturé et interdit un rejeu automatique. Un payload vide se termine proprement avec `NOT_VIABLE` au lieu de provoquer un crash.

## MLOps

Le mode `start_next_stage` exige un préflight exact. Le mode `continue_current_stage` revalide également le préflight, son identifiant et le `candidate_plan_id`. Une altération du plan candidat bloque la reprise.

Aucune promotion de modèle n'est déclenchée par le préflight ou la campagne.

## SRE / Release

Le nouveau workflow partage le verrou `production-change`, évitant une consommation concurrente de crédits avec les autres opérations. Les déploiements Railway restent détachés puis vérifiés publiquement ; aucun retour au streaming de logs bloquant n'a été introduit.

Le préflight ne déploie pas la production. Il publie des artefacts et, selon le fonctionnement existant du dépôt, commit le rapport de décision.

## Sécurité

Les entrées utilisateur du nouveau workflow sont transférées via des variables d'environnement et non interpolées directement dans le shell. Les rapports n'embarquent ni clé API ni URL de base de données.

Risques résiduels : actions GitHub non figées par SHA, stockage limité des preuves et migrations de schéma encore sans Alembic.

## QA

Validation réalisée :

- 181 tests réussis par quatre lots ;
- 0 échec ;
- couverture cœur `sports_predictor + webapp` : 83 % ;
- module V4.2 `coverage_preflight.py` : 87 % ;
- compilation Python réussie ;
- syntaxe JavaScript réussie ;
- 12 workflows GitHub et `render.yaml` parsés ;
- aucun `railway up --ci` dans les workflows.

Les régressions V4.2 couvrent notamment : faible couverture réelle, sur-échantillonnage, budget insuffisant, consensus incomplet, séparation Pinnacle, reprise, facturation incertaine, réponse fournisseur vide, fichier candidat altéré et synchronisation du plan intégré.

## Responsable usage

Les invariants sont conservés : aucune mise, aucun pari automatique, aucune promesse de rentabilité et aucune promotion automatique. Les résultats sportifs ne servent jamais à choisir la période ou les événements du préflight.

## Arbitrage final

La V4.2 ne cherche pas encore à améliorer le modèle. Elle améliore la qualité de la décision d'acheter de la donnée. C'est le meilleur usage de la prochaine version au vu de la campagne réelle : la technique fonctionnait, mais la disponibilité de la baseline ne justifiait pas le coût du backfill.
