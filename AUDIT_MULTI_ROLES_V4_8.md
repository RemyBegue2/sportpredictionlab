# Audit multi-rôles — Sports Prediction Lab V4.8.0

## Verdict consolidé

- **Accélération des preuves : GO.** Le football est diagnostiqué par sous-groupes et le tennis dispose d’un import versionné, audité et mis en quarantaine.
- **Interface compacte : GO.** Aucun nouvel onglet simple ; une phrase d’action est ajoutée à Aujourd’hui et les détails restent progressifs.
- **Stabilité publique longue session : GO pour workflow, à exécuter en production.** Le test mesure DOM, requêtes, erreurs et chargement expert.
- **Alembic : GO.** Les nouvelles tables sont gérées par migrations avec adoption contrôlée du schéma existant.
- **Actions GitHub : GO.** Toutes les références `actions/*` sont figées par SHA complet.
- **Entraînement et analyse : zéro crédit fournisseur.**
- **Promotion automatique, pari réel et mise personnalisée : NO-GO.**

## Product Owner

### Retour

La priorité n’est plus d’ajouter des panneaux ou des modèles, mais de rendre les blocages lisibles : pourquoi le football reste en hold, pourquoi le tennis ne peut pas encore être entraîné sérieusement et quelle action vient ensuite.

### Corrections retenues

- exactement trois onglets simples ;
- une synthèse `À retenir` dans Aujourd’hui ;
- Apprentissage affiche football, tennis, preuve live et coût ;
- le détail des datasets, holdouts et sous-groupes reste dans les panneaux repliables ;
- aucun nouvel objet technique dans le premier écran.

## UX / stabilité frontend

### Retour

La stabilité longue session devait devenir une preuve mesurable et non un simple enchaînement de dix clics.

### Corrections retenues

- conservation des protections V4.7 : GET dédupliqués, timeout, annulation et DOM plafonné ;
- script navigateur paramétrable jusqu’à 3 600 secondes ;
- mesure des nœuds DOM, ressources réseau et mémoire lorsque Chromium l’expose ;
- échec si le DOM ou les requêtes croissent sans borne ;
- rapport JSON systématique ;
- workflow public recommandé à 1 800 secondes ;
- aucune donnée fournisseur chargée par ce test.

## Quant / statisticien

### Retour

Un challenger football en hold ne doit pas conduire à tester arbitrairement des dizaines de modèles. Un même holdout ne doit pas être exploité indéfiniment.

### Corrections retenues

- diagnostic par outcome, saison, forme de marché, maturité des équipes et repos ;
- maximum de deux challengers football pour le prochain tour ;
- sélection probabiliste, jamais par ROI in-sample ;
- génération de holdout identifiée `HG-*` ;
- frontières train/calibration/holdout enregistrées ;
- aucun remplacement du champion.

Le rapport réel montre une dégradation globale du log loss du challenger d’environ **+0,0307** face à la baseline. Les plus fortes régressions concernent le nul, le repos déséquilibré et les victoires extérieures. Le verdict `hold_explained` est donc cohérent.

## Ingénieur ML football

### Retour

Le modèle linéaire V4.7 améliore certaines victoires à domicile mais se dégrade fortement sur les nuls et les victoires extérieures. Cette asymétrie doit être comprise avant tout nouveau modèle.

### Corrections retenues

- conservation du champion ;
- publication des cinq plus grandes régressions et améliorations ;
- prochain tour limité à :
  1. Poisson régularisé attaque/défense ;
  2. hybride linéaire attaque/défense/Elo ;
- aucun entraînement automatique de ces deux candidats dans cette version ;
- seuils V4.7 maintenus.

## Ingénieur ML tennis

### Retour

Les 32 matchs répartis sur deux dates ne permettent ni calibration sérieuse ni comparaison multi-surface.

### Corrections retenues

Le nouvel import :

- normalise joueurs, surfaces, tours et tournois ;
- accepte plusieurs alias de colonnes ;
- détecte les doublons ;
- refuse un classement publié après le match ;
- marque les anciennes lignes sans timestamp comme `legacy_unverified` ;
- produit un hash par ligne et un hash de dataset ;
- calcule la couverture par surface et le nombre de dates ;
- garde le statut réel `collecting`.

Les portes proposées sont de 500 matchs et 50 dates pour une exploration, puis 1 500 matchs et 150 dates pour un challenger sérieux. Elles ne sont pas artificiellement abaissées pour faire passer l’archive livrée.

## Data Engineer

### Retour

Une correction de dataset ne doit jamais écraser silencieusement la preuve précédente.

### Corrections retenues

- catalogue append-only `dataset_catalog` ;
- identifiant déterministe `DS-*` ;
- `dataset_sha256`, cutoff, source, licence, qualité et dataset remplacé ;
- table append-only `holdout_generations` ;
- identifiant déterministe `HG-*` ;
- lignes invalides dans un export de quarantaine séparé ;
- même contenu dans un autre ordre = même hash ;
- modification de contenu = nouveau hash.

## FinOps

### Retour

Enrichir les preuves ne doit pas rouvrir The Odds API.

### Corrections retenues

- import tennis local : zéro crédit ;
- diagnostic football : zéro crédit ;
- Feature Lab et Challenger Factory : zéro crédit ;
- workflow Evidence Acceleration sans secret fournisseur ;
- assertions CI : `provider_credits_consumed == 0` ;
- captures live payantes toujours séparées et fermées par défaut.

## SRE / MLOps

### Retour

Le laboratoire, les migrations et le test longue session ne doivent pas bloquer le produit quotidien.

### Corrections retenues

- endpoints GET en lecture seule ;
- POST protégé par `RUN_EVIDENCE_ACCELERATION` ;
- rapport persisté dans le benchmark append-only ;
- workflow indépendant avec timeout de 20 minutes ;
- test longue session indépendant avec timeout de 40 minutes ;
- champion actuel conservé après tout échec ;
- `/api/ready` indépendant d’un résultat de laboratoire négatif.

## Sécurité

### Retour

Les deux dettes P1 persistantes devaient enfin être traitées sans inventer de références.

### Corrections retenues

- Alembic introduit avec baseline pré-V4.8 et migration des nouvelles tables ;
- upgrade et downgrade testés sur SQLite ;
- Railway et Render exécutent déjà `scripts.db_migrate` avant le déploiement ;
- toutes les actions GitHub utilisées sont figées sur un SHA complet ;
- commentaires conservant la version humaine ;
- test CI refusant toute référence flottante ;
- aucune désérialisation arbitraire ;
- paramètres et rapports JSON portables.

## QA

### Résultats

- **261 tests collectés** ;
- **261 tests réussis** en six lots disjoints ;
- **0 échec** ;
- 8 nouveaux tests V4.8 ;
- `evidence_acceleration.py` : **94 %** de couverture ciblée avec branches ;
- `challenger_factory.py` : **90 %** sur le même lot ciblé ;
- compilation de 86 fichiers Python ;
- syntaxe JavaScript valide ;
- 22 workflows YAML valides ;
- upgrade/downgrade Alembic vérifié ;
- actions GitHub figées vérifiées ;
- tests frontend : trois onglets, huit cartes maximum, action claire et rendu Evidence Acceleration.

## Usage responsable

La V4.8 conserve :

- probabilités et signaux uniquement expérimentaux ;
- bankrolls fictives uniquement ;
- aucune bankroll réelle ;
- aucune taille de mise personnalisée ;
- aucun placement de pari ;
- aucune connexion bookmaker ;
- aucune martingale ;
- aucune promesse de rendement ;
- abstention comme résultat valide.

## Limites assumées

- le workflow public de 30 minutes est fourni mais n’a pas été exécuté contre le déploiement de l’utilisateur depuis l’environnement de préparation ;
- l’archive tennis livrée reste limitée à 32 matchs et deux dates ;
- les deux challengers football proposés ne sont pas entraînés tant que l’analyse du hold n’est pas revue ;
- les anciennes observations sans timestamps de disponibilité restent `legacy_unverified` ;
- aucune rentabilité n’est revendiquée.

## Décision finale

V4.8.0 est prête pour un déploiement contrôlé. Elle traite les dettes structurelles au lieu d’ajouter de la complexité : preuve tennis versionnée, hold football expliqué, migrations réelles, CI figée et test public longue session mesurable. Les dépenses fournisseur et la promotion automatique restent fermées.
