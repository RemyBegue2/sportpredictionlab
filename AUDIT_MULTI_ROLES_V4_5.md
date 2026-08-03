# Audit multi-rôles — Sports Prediction Lab V4.5.0

## Verdict consolidé

- **Interface simple : GO.**
- **Automatisation shadow : GO sous double activation et plafond quotidien partagé.**
- **Entraînement hebdomadaire des challengers : GO, zéro crédit fournisseur.**
- **Promotion du champion : GO uniquement après revue humaine.**
- **Paris réels, mise personnalisée et promotion automatique : NO-GO.**

## Product Owner

### Retour initial

La V4.4 était fonctionnelle mais affichait simultanément trop de panneaux : produit quotidien, fournisseur, base, shadow, benchmark, evidence, campagne, modèles et audit. L’utilisateur devait comprendre l’architecture avant de trouver l’information utile.

### Correction retenue

La V4.5 réduit le premier parcours à trois questions :

1. quels matchs sont analysés aujourd’hui ;
2. existe-t-il un signal shadow ;
3. quelle est la prochaine action de collecte ou d’apprentissage.

Les simulations et détails d’entraînement sont repliés. Le mode expert reste disponible sans supprimer les outils historiques.

## UX / accessibilité

### Retour initial

Masquer visuellement les panneaux ne suffisait pas si l’application continuait à charger toutes leurs données et à produire des alertes techniques au démarrage.

### Correction retenue

- `simple-mode` est le mode initial ;
- les sections expertes portent `data-view="expert"` ;
- leurs endpoints sont chargés seulement après activation du mode expert ;
- le choix est mémorisé localement ;
- le smoke test Chromium valide d’abord la vue simple, puis le chargement différé expert ;
- toute erreur JavaScript ou interface partielle reste bloquante.

## Quant / statisticien

### Retour initial

Une automatisation qui entraîne chaque semaine peut multiplier les essais jusqu’à trouver un ROI flatteur par hasard. Un statut `candidate` V4.4 n’était pas suffisant pour devenir champion.

### Correction retenue

Le challenger doit passer des portes plus strictes que les portes d’entraînement :

- 100 événements réglés au total ;
- 20 signaux sur le holdout ;
- 60 événements football ;
- 60 événements tennis ;
- politique et méta-modèle tous deux candidats ;
- drawdown holdout inférieur au plafond pré-enregistré ;
- au moins trois folds évaluables et 60 % de folds non négatifs ;
- non-dégradation contrôlée face au champion lorsqu’il existe.

Le système publie `collecting`, `hold` ou `review_required`. Il ne publie jamais `promoted` automatiquement.

## Ingénieur ML

### Retour initial

Un artefact challenger devait être identifiable, reproductible et comparable sans chargement arbitraire de code sérialisé.

### Correction retenue

- identifiant stable `RCH-*` dérivé de la politique, des fenêtres et des paramètres portables ;
- paramètres du méta-modèle conservés sous forme de coefficients, normalisation et intercept ;
- comparaison champion/challenger recalculée depuis les observations réglées ;
- aucune modification des modèles sportifs directement sur le ROI ;
- aucune levée des règles spécifiques au tennis sans échantillon propre à ce sport.

## Data Engineer

### Retour initial

Le plafond de crédits V4.4 était principalement contrôlé par requête. Une capture et un règlement séparés pouvaient chacun respecter leur plafond tout en dépassant la limite quotidienne globale.

### Correction retenue

Les lignes `BenchmarkRunRecord` existantes servent de registre append-only des coûts. Le calcul journalier additionne uniquement :

- `daily_live_market_shadow` ;
- `daily_result_settlement` ;
- `automated_shadow_cycle`.

Les optimisations zéro crédit ne sont pas comptées. La date est interprétée en `Europe/Paris` avec validation stricte `YYYY-MM-DD`.

## FinOps

### Retour initial

L’automatisation ne devait pas transformer un plafond manuel de trois crédits en trois crédits par tâche ou en appel inutile les jours sans football.

### Correction retenue

- budget commun à la capture et au règlement ;
- maximum automatisé de trois crédits ;
- vérification gratuite du calendrier avant une capture football automatisée ;
- journée sans fixture : aucun appel football payant ;
- aucun résultat dû : règlement no-op à zéro crédit, même si le budget du jour est épuisé ;
- entraînement hebdomadaire : zéro appel fournisseur ;
- dashboard : consommé, plafond et restant sur la même journée locale.

## SRE / MLOps

### Retour initial

Les tâches capture, règlement et entraînement devaient être idempotentes, observables et ne pas se concurrencer lors d’un cycle manuel.

### Correction retenue

Le workflow `Automated shadow learning cycle` propose :

- capture quotidienne conditionnelle ;
- règlement toutes les six heures ;
- optimisation hebdomadaire ;
- action manuelle `cycle` avec règlement avant capture ;
- artefacts de capture, règlement et challenger ;
- concurrence unique `automated-shadow-learning` ;
- activation requise à la fois dans GitHub et dans l’application.

La promotion est isolée dans un workflow manuel distinct et protégé par l’environnement `production`.

## Sécurité

### Retour initial

L’automatisation augmente la surface d’action. Elle ne devait pas permettre une promotion ou une dépense par simple appel non authentifié.

### Correction retenue

- endpoints d’écriture sous authentification et CSRF existants ;
- confirmations exactes pour capture, règlement et promotion ;
- candidat limité au format `RCH-[A-F0-9]{20}` ;
- décision de promotion enregistrée avec note humaine ;
- aucune clé dans l’interface ;
- aucune désérialisation arbitraire ;
- aucune connexion bookmaker.

Les actions GitHub restent majoritairement référencées par tags majeurs. Leur fixation par SHA demeure un risque P1 ; aucun SHA n’a été inventé pendant cette livraison.

## QA

### Résultats

- 235 tests collectés ;
- 235 réussis par lots disjoints ;
- 0 échec ;
- couverture globale combinée avec branches : 78,3 % ; couverture des instructions : 83,0 % ;
- compilation Python réussie ;
- syntaxe JavaScript réussie ;
- tous les YAML analysables ;
- tests Node du rendu quotidien et apprentissage ;
- smoke Chromium renforcé simple puis expert.

### Régressions V4.5 couvertes

- challenger reproductible et manuel ;
- portes par sport ;
- trajectoire de bankroll fictive ;
- vue simple par défaut ;
- chargement expert différé ;
- journée vide sans appel football payant ;
- budget quotidien partagé ;
- règlement no-op sans crédit ;
- feature flag d’automatisation ;
- promotion refusée avant les portes ;
- promotion manuelle sans action automatique ;
- workflows bornés.

## Usage responsable

Les simulations contiennent une `simulated_stake` pour reconstruire la trajectoire fictive. Cette valeur n’est jamais calculée à partir de la bankroll réelle de l’utilisateur et n’est jamais transmise à un bookmaker.

La V4.5 conserve :

- aucune mise réelle ou personnalisée ;
- aucun placement automatique ;
- aucune martingale ;
- aucune promesse de rendement ;
- l’abstention comme résultat valide.

## Limites assumées

- aucun cycle automatisé réel n’a été exécuté depuis l’environnement de préparation ;
- aucun crédit réel n’a été consommé ;
- aucun challenger réel ne dispose encore des échantillons de promotion ;
- le modèle tennis reste une baseline Elo non calibrée tant que sa preuve spécifique est insuffisante ;
- le registre utilise les tables existantes, donc aucune migration de schéma n’était nécessaire pour cette version ; Alembic reste requis avant une future modification complexe de base ;
- la performance financière simulée n’est pas une preuve de rentabilité future.

## Décision finale

La V4.5.0 est prête pour un déploiement contrôlé. Déployer d’abord avec l’automatisation et les crédits fermés. Après vérification de la vue simple, activer éventuellement un cycle shadow borné. La promotion du champion reste manuelle, même lorsque toutes les portes sont au vert.
