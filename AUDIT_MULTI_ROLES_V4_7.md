# Audit multi-rôles — Sports Prediction Lab V4.7.0

## Verdict consolidé

- **Cockpit stable longue session : GO.** Les requêtes GET identiques sont dédupliquées, bornées par timeout et annulées à la fermeture de page.
- **Interface simple : GO.** Un seul onglet reste visible, les listes sont plafonnées à huit cartes et les détails restent progressifs.
- **Challenger football réel : GO recherche, verdict `hold`.** Le modèle linéaire régularisé a été entraîné et évalué sur un holdout chronologique réel, mais il ne bat pas suffisamment la baseline Elo.
- **Challenger tennis : collecte.** Le code surface-aware est opérationnel, mais l’archive embarquée ne contient que 32 matchs et deux dates distinctes ; aucune preuve n’est inventée.
- **Crédits fournisseur pour l’entraînement : zéro.**
- **Promotion automatique, pari réel, mise personnalisée : NO-GO.**

## Product Owner

### Retour

La V4.6 était plus compacte, mais une journée riche pouvait encore afficher de longues listes et rendre la décision principale difficile à trouver.

### Corrections

- huit cartes maximum par liste dans le mode simple ;
- nombre d’éléments masqués explicitement affiché ;
- quatre cartes d’apprentissage seulement : football, tennis, preuve live et coût ;
- aucune nouvelle section principale ;
- le mode expert conserve les détails complets.

## UX / stabilité frontend

### Retour

Le signalement « ça bugue au bout d’un moment » est compatible avec plusieurs défauts de session longue : requêtes répétées après plusieurs clics, réponses anciennes arrivant en retard, trop de cartes dans le DOM, erreurs expertes répétées et toasts qui se chevauchent.

### Corrections

- déduplication des GET concurrents par URL ;
- timeout de 12 secondes avec `AbortController` lorsque disponible ;
- annulation des requêtes actives au `pagehide` ;
- compteur de session visible : requêtes et erreurs récupérées ;
- un seul toast actif à la fois ;
- chargement expert mutualisé et réessayable après un échec partiel ;
- boutons de rafraîchissement désactivés pendant leur requête ;
- listes quotidiennes, à venir et signaux plafonnées à huit cartes ;
- smoke test renforcé avec navigation répétée entre les trois onglets.

## Quant / statisticien

### Retour

Un vrai challenger doit être évalué sur des observations jamais utilisées pour l’entraînement ou la calibration. Le ROI ne doit pas servir de fonction de perte du modèle sportif.

### Corrections

- split chronologique par groupes de dates : entraînement, calibration, holdout ;
- dates identiques jamais coupées entre partitions ;
- football : régression logistique multinomiale régularisée, calibrée par température ;
- tennis : régression logistique surface-aware, calibrée par température ;
- sélection uniquement sur log loss, Brier, calibration et stabilité ;
- ROI absent du processus d’entraînement ;
- statut `candidate`, `hold` ou `collecting`, jamais promotion automatique.

## Ingénieur ML football

Le challenger utilise douze caractéristiques pré-match reproductibles : Elo, forme offensive/défensive, contexte domicile/extérieur, taux de buts du championnat, repos et expérience cumulée.

Sur l’archive EPL locale :

- 1 900 matchs ;
- 583 dates distinctes ;
- 1 106 lignes d’entraînement ;
- 401 lignes de calibration ;
- 393 lignes de holdout ;
- verdict final : `hold`.

Le résultat `hold` est positif du point de vue gouvernance : le système a réellement entraîné un challenger et a conservé le champion lorsque la preuve n’était pas suffisante.

## Ingénieur ML tennis

Le pipeline surface-aware est fonctionnel et testé sur un historique synthétique multi-surface. Il utilise notamment Elo global, Elo surface, classement, points, forme récente, repos, charge et format.

L’archive tennis livrée reste insuffisante : 32 lignes sur seulement deux dates. Le système publie donc `collecting` et refuse de présenter un modèle tennis entraîné comme validé.

## Data Engineer

- chaque dataset produit un identifiant `DS-*` et un SHA-256 déterministe ;
- l’ordre des lignes ne modifie pas le hash ;
- toute modification de contenu modifie le hash ;
- le cutoff, le nombre de lignes et les dates distinctes sont enregistrés ;
- les paramètres du modèle restent portables : features, normalisation, coefficients, intercept, classes et température ;
- aucune désérialisation arbitraire n’est ajoutée.

## FinOps

- aucun appel à The Odds API ;
- aucun secret fournisseur dans le workflow Challenger Factory ;
- maximum annoncé de quatre modèles par sport, vingt configurations par modèle et cinq folds ;
- entraînement ignoré implicitement lorsque l’historique tennis ne passe pas les seuils ;
- le dashboard lit le dernier rapport PostgreSQL ou l’artefact local sans lancer d’entraînement.

## SRE / MLOps

- endpoint GET en lecture seule : `/api/challenger-factory` ;
- endpoint POST protégé par confirmation exacte : `/api/challenger-factory/run` ;
- workflow séparé, timeout 25 minutes, concurrence unique ;
- rapport persisté dans le registre de benchmark et exporté comme artefact ;
- un échec du challenger ne bloque ni `/api/ready` ni le champion actuel ;
- les données expertes ne sont pas chargées tant que le mode expert reste fermé.

## Sécurité

- confirmation `RUN_CHALLENGER_FACTORY` obligatoire ;
- endpoint d’écriture protégé par l’authentification et le CSRF existants ;
- aucun secret dans l’interface ;
- paramètres de modèles au format JSON portable ;
- aucune action bookmaker ;
- aucune promotion automatique.

Les actions GitHub restent principalement référencées par tags majeurs et Alembic n’est toujours pas introduit. Ces deux sujets restent P1 et ne sont pas falsifiés avec des SHA inventés ou une migration artificielle.

## QA

- 253 tests collectés ;
- 253 tests réussis en cinq lots disjoints ;
- 0 échec ;
- huit nouveaux tests V4.7 ;
- déduplication des GET exécutée dans Node ;
- plafond de huit cartes vérifié dans Node ;
- entraînement tennis multi-surface testé ;
- hash dataset testé ;
- confirmation POST testée ;
- workflow zéro crédit testé ;
- navigation répétée ajoutée au smoke Chromium.

## Usage responsable

Les modèles, signaux et bankrolls restent des outils de recherche. La V4.7 ne traite aucune bankroll réelle, ne calcule aucune mise personnalisée, ne place aucun pari, ne se connecte à aucun bookmaker et ne promet aucun rendement.

## Risques résiduels

- aucun smoke Chromium longue session n’a été exécuté contre le déploiement public depuis l’environnement d’audit ;
- le challenger football est `hold`, pas meilleur que le champion selon les portes ;
- l’historique tennis multi-surface réel est insuffisant ;
- actions GitHub non toutes figées par SHA ;
- Alembic absent ;
- rate limiter local au processus ;
- rétention des preuves dépend de la politique opérationnelle.

## Décision finale

V4.7.0 est prête pour un déploiement contrôlé. Le bénéfice immédiat est la stabilité du cockpit pendant une session longue et une Challenger Factory honnête : football réellement évalué, tennis explicitement bloqué faute de données, zéro crédit et aucune promotion automatique.
