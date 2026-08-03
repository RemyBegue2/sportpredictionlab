# Résultats vérifiés — V4.0

## Validation automatisée

- 145 tests réussis, 0 échec ;
- couverture globale du package `sports_predictor` : 83 % ;
- 11 workflows GitHub Actions analysés par le parseur YAML ;
- compilation Python réussie ;
- syntaxe JavaScript validée avec `node --check` ;
- endpoint `/api/release` vérifié en test avec la version `4.0.0` ;
- endpoint `/api/evidence-campaign` vérifié ;
- plan de stage 100 généré puis validé en dry-run avec un plan fournisseur immuable ;
- planner de campagne testé avec une `DATABASE_URL` volontairement invalide : aucun accès SQLAlchemy ;
- restauration locale d’un checkpoint compatible vérifiée ;
- refus des budgets insuffisants vérifié ;
- conservation des dates d’une campagne continuée vérifiée.

## Cas de référence vérifié

Pour un stage 30 avec un coût observé ou prudent de 10 crédits par snapshot, 14 appels de découverte et un plafond de 350 crédits :

- capacité estimée : 33 snapshots ;
- cible sélectionnée : 30 ;
- exécution du stage autorisable après confirmation ;
- aucune saisie de `plan_id` ;
- aucune dépendance PostgreSQL.

## Limites de la validation

- aucun appel réel The Odds API n’a été lancé dans cet environnement ;
- aucun crédit fournisseur n’a été consommé ;
- aucun déploiement sur le Railway de l’utilisateur n’a été déclenché ;
- la récupération d’un artefact depuis l’API GitHub ne peut être testée ici contre le dépôt réel ; la logique de compatibilité et de restauration a été testée localement ;
- les coûts réels peuvent différer du coût prudent utilisé par le plan ; le plafond global reste bloquant pendant l’exécution ;
- aucune conclusion statistique sur le modèle n’est produite par cette livraison.
