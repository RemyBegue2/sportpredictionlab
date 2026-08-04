# Audit multi-rôles — Sports Prediction Lab V4.9.0

## Verdict consolidé

- **Décision modèle contrôlée : GO recherche.** Deux challengers football maximum sont réellement entraînés, mais aucun n’est promotion-ready.
- **Protection du holdout : GO.** Le holdout V4.7/V4.8 déjà consulté reste diagnostic-only ; une nouvelle génération future est ouverte.
- **Tennis incrémental : GO.** Les ajouts, doublons et corrections produisent une nouvelle version sans écraser l’ancienne.
- **Validation publique : GO pour le workflow, encore à exécuter.** Les scénarios simple et expert sont séparés.
- **Interface compacte : GO.** Toujours trois onglets et quatre cartes d’apprentissage.
- **Entraînement, import et validation navigateur : zéro crédit fournisseur.**
- **Promotion automatique, pari réel et mise personnalisée : NO-GO.**

## Product Owner

### Retour

La V4.8 avait préparé les décisions, mais l’utilisateur devait encore déduire si un modèle pouvait réellement changer. La V4.9 devait afficher une décision nette sans ajouter un quatrième onglet.

### Correction retenue

- exactement trois onglets : Aujourd’hui, Signaux, Apprentissage ;
- Apprentissage montre football, tennis, production et coût ;
- traduction simple des états techniques ;
- détails des expériences et holdouts repliés ;
- aucune promotion présentée comme acquise.

## UX / frontend

### Retour

Les états `hold_explained`, `development_candidate` et `open_collecting` sont utiles à l’audit mais trop techniques pour la vue simple.

### Correction retenue

- `hold` devient « le nouveau modèle est moins bon » ou « champion conservé » ;
- la progression tennis est affichée comme `32 / 500 matchs` ;
- la production affiche « validée » uniquement si les deux sessions longues passent ;
- le mode expert conserve les identifiants, hashes et métriques ;
- le DOM reste borné et aucun nouvel onglet n’est ajouté.

## Quant / statisticien

### Retour

Le holdout déjà consulté ne pouvait pas être réutilisé pour régler les nouveaux challengers. Sinon, la V4.9 aurait optimisé indirectement sur la preuve finale.

### Correction retenue

- 393 matchs du holdout historique restent `consulted_diagnostic_only` ;
- les nouveaux modèles utilisent uniquement une zone de développement antérieure ;
- split de développement : 1 028 entraînement, 250 calibration, 229 validation ;
- nouvelle génération de promotion ouverte après le 24 mai 2026 ;
- 30 nouvelles dates distinctes requises ;
- promotion impossible avec la génération actuelle ;
- ROI absent de la fonction d’entraînement.

## Ingénieur ML football

### Challenger 1 — Poisson régularisé attaque/défense

- log loss développement : **0,9850** ;
- baseline Elo : **0,9945** ;
- ECE : **0,0525** contre **0,0465** ;
- verdict : `hold` ;
- veto : matchs nuls et repos déséquilibré.

Le modèle progresse globalement en log loss, mais la gouvernance refuse de sacrifier les sous-groupes déjà identifiés comme fragiles.

### Challenger 2 — Hybride Poisson/Elo

- log loss développement : **0,9868** ;
- ECE : **0,0750** ;
- verdict : `hold` ;
- causes : ECE hors tolérance, matchs nuls et repos déséquilibré.

### Décision

Le champion reste actif. Aucun des deux challengers n’est évalué sur le futur holdout de promotion, qui n’existe pas encore.

## Ingénieur ML tennis

### Retour

Le blocage reste la preuve, pas l’algorithme.

### Correction retenue

- progression visible : 32 / 500 matchs et 2 / 50 dates pour exploration ;
- challenger sérieux toujours bloqué avant 1 500 matchs et 150 dates ;
- aucun entraînement tennis sous les seuils ;
- imports incrémentaux compatibles avec plusieurs lots ;
- doublons inchangés ignorés ;
- corrections de résultat versionnées ;
- données futures mises en quarantaine.

## Data Engineer

### Retour

Un import incrémental ne devait ni dupliquer les matchs ni modifier silencieusement un dataset existant.

### Correction retenue

- `supersedes_dataset_id` obligatoire pour l’import incrémental ;
- match key déterministe par date, tournoi et paire de joueurs ;
- doublons identiques conservés une seule fois ;
- correction de résultat remplace la ligne dans la nouvelle version uniquement ;
- ancien dataset conservé ;
- nouveau hash de dataset après modification ;
- statistiques d’ajouts, corrections et quarantaine publiées.

## FinOps

- modèles football : zéro appel fournisseur ;
- import tennis : zéro appel fournisseur ;
- validation longue session : zéro appel fournisseur ;
- maximum deux challengers football ;
- trois alphas Poisson et trois poids hybrides seulement ;
- aucune campagne historique payante réactivée.

## SRE / MLOps

### Correction retenue

- endpoint GET : `/api/controlled-model-decision` ;
- POST protégé par `RUN_CONTROLLED_MODEL_DECISION` ;
- workflow dédié, timeout 30 minutes et concurrence unique ;
- rapport append-only dans le registre benchmark ;
- deux scénarios de longue session exécutés séparément ;
- échec d’un challenger sans effet sur `/api/ready` ;
- champion actuel conservé.

## Sécurité

- actions GitHub toujours figées par SHA complets ;
- permissions du nouveau workflow limitées à `contents: read` ;
- aucune clé fournisseur dans les workflows V4.9 ;
- paramètres des modèles au format JSON portable ;
- hashes obligatoires ;
- aucune désérialisation arbitraire ;
- confirmation exacte pour les écritures ;
- aucune action bookmaker.

## QA

- **266 tests collectés** ;
- **266 tests réussis** en six lots disjoints ;
- **0 échec** ;
- 5 nouveaux tests V4.9 ;
- `controlled_decision.py` : **89 %** de couverture ciblée avec branches ;
- compilation de 89 fichiers Python ;
- syntaxe JavaScript valide ;
- 23 workflows YAML valides ;
- 53 références `actions/*` figées par SHA complet ;
- tests d’import incrémental, correction de résultat, holdout futur, API et interface.

## Usage responsable

La V4.9 conserve :

- probabilités et signaux uniquement expérimentaux ;
- bankrolls fictives uniquement ;
- aucune bankroll réelle ;
- aucune taille de mise personnalisée ;
- aucun placement de pari ;
- aucune connexion bookmaker ;
- aucune martingale ;
- aucune promesse de rendement ;
- abstention comme décision valide.

## Limites assumées

- les deux sessions longues publiques ne sont pas exécutées depuis l’environnement de préparation ;
- la nouvelle génération de holdout football contient encore zéro date future ;
- les deux challengers football restent en `hold` ;
- l’historique tennis livré reste limité à 32 matchs et deux dates ;
- aucun ROI réel n’est revendiqué.

## Décision finale

V4.9.0 est prête pour un déploiement contrôlé. Elle produit une vraie décision négative plutôt qu’un faux progrès : le champion football reste actif, le tennis reste bloqué sous ses seuils et la stabilité publique doit encore être prouvée par les deux scénarios longue session. Les dépenses fournisseur et la promotion automatique restent fermées.
