# Audit multi-rôles — Sports Prediction Lab V4.6.0

## Verdict consolidé

- **Cockpit compact : GO.** La vue simple n’affiche qu’un écran à la fois : Aujourd’hui, Signaux ou Apprentissage.
- **Calibration football et tennis : GO recherche.** Les calibrateurs sont sélectionnés sur une fenêtre antérieure puis soumis à un holdout chronologique qui peut les refuser.
- **Feature Lab : GO borné et zéro crédit.** Les expériences sont pré-enregistrées, limitées et ne contactent aucun fournisseur.
- **Promotion automatique : NO-GO.** Un calibrateur candidat ne modifie pas le champion actif.
- **Pari réel, mise personnalisée et promesse de rendement : NO-GO.**

## Product Owner

### Retour

La V4.5 avait réduit le nombre de panneaux visibles, mais la page simple conservait encore une longue succession d’informations. L’utilisateur devait faire défiler Aujourd’hui, Signaux et Apprentissage alors qu’il cherchait une seule réponse à la fois.

### Correction retenue

- un seul panneau principal est visible en mode simple ;
- le panneau initial est `Aujourd’hui` ;
- la navigation bascule explicitement vers `Signaux` ou `Apprentissage` ;
- le grand hero et les statistiques techniques sont supprimés de la vue simple ;
- le mode expert conserve toutes les fonctions existantes.

## UX / accessibilité

### Retour

La simplification doit être comportementale, pas seulement cosmétique.

### Correction retenue

- état actif persistant dans `localStorage` ;
- onglet actif visible ;
- aucun second panneau primaire affiché simultanément ;
- navigation clavier conservée via des liens standards ;
- smoke Chromium renforcé : Aujourd’hui, puis Signaux, puis Apprentissage, puis mode expert ;
- erreur JavaScript et interface partielle toujours bloquantes.

## Quant / statisticien

### Retour

Un calibrateur ne doit pas être retenu parce qu’il améliore le même échantillon utilisé pour le choisir.

### Correction retenue

- séparation chronologique calibration/holdout ;
- interdiction de couper un groupe d’horodatages identiques ;
- sélection bornée : identité et temperature scaling pour le football ; identité, temperature scaling et Platt pour le tennis ;
- veto du holdout en cas de dégradation du log loss ou de l’ECE ;
- ROI absent du critère de sélection des calibrateurs ;
- statut `candidate`, `hold` ou `collecting`, jamais `promoted`.

## Ingénieur ML

### Retour

Football et tennis ne doivent pas partager un calibrateur ou une preuve commune.

### Correction retenue

- rapports distincts par sport ;
- cible football 1N2 ordonnée `away/draw/home` ;
- cible tennis binaire joueur 1/joueur 2 ;
- paramètres portables uniquement ;
- identifiant stable `EXP-*` pour chaque expérience pré-enregistrée ;
- maximum de quatre calibrateurs et douze expériences par sport ;
- les modèles sportifs ne sont pas réentraînés directement sur le ROI.

## Data Engineer

### Retour

Une nouvelle feature ne doit jamais entrer dans une expérience si elle est devenue disponible après la prédiction.

### Correction retenue

- audit `feature_manifest` ;
- comparaison de `available_at` avec `prediction_created_at` ;
- toute feature future est signalée comme `future_feature` ;
- les anciennes lignes sans manifeste restent lisibles pour continuité, mais les nouvelles expériences doivent publier leur lineage ;
- rapport du nombre de manifestes, features vérifiées et violations temporelles.

## FinOps

### Retour

L’entraînement et la calibration ne doivent pas rouvrir le fournisseur.

### Correction retenue

- endpoint et script Feature Lab exclusivement alimentés par PostgreSQL ;
- workflow hebdomadaire sans secret The Odds API ;
- `provider_credits_consumed = 0` vérifié par test et dans l’artefact ;
- aucun changement des plafonds de capture V4.5.

## SRE / MLOps

### Retour

Une expérience de calibration ne doit pas perturber le produit quotidien.

### Correction retenue

- `/api/feature-lab` est en lecture seule et sans fournisseur ;
- `/api/feature-lab/run` exige `RUN_FEATURE_LAB` ;
- workflow séparé, timeout 20 minutes, concurrence unique ;
- résultat persisté comme benchmark append-only ;
- un échec du laboratoire ne bloque pas `/api/ready` ni le champion existant.

## Sécurité

### Retour

Ne pas inventer de SHA d’actions GitHub et ne pas introduire une migration de schéma sans besoin réel.

### Arbitrage

- permissions du nouveau workflow limitées à `contents: read` ;
- aucune clé fournisseur ;
- aucune désérialisation arbitraire ;
- confirmation exacte sur l’écriture ;
- cette version réutilise le registre append-only existant et ne modifie pas le schéma ; Alembic reste P1 avant une vraie modification de tables ;
- la fixation de toutes les actions par SHA reste P1 et doit être réalisée avec des SHA officiels vérifiés, pas devinés.

## QA

- 245 tests collectés ;
- 245 réussis en sept lots disjoints ;
- 0 échec ;
- 10 nouveaux tests V4.6 ;
- module `feature_lab.py` : 79 % de couverture combinée branches/instructions sur le lot instrumenté ;
- compilation de 83 fichiers Python ;
- syntaxe JavaScript valide ;
- 20 YAML analysés ;
- test Node du rendu Feature Lab ;
- test de confirmation POST ;
- test du workflow zéro crédit ;
- scénario quotidien rendu indépendant de l’heure d’exécution.

## Usage responsable

La fiabilité affichée signifie uniquement `élevée/moyenne/faible/données insuffisantes` pour la recherche probabiliste. Elle ne prédit pas la réussite d’un pari individuel.

La V4.6 conserve :

- aucune mise réelle ;
- aucune taille de mise personnalisée ;
- aucun placement automatique ;
- aucune connexion bookmaker ;
- aucune martingale ;
- aucune promesse de rentabilité ;
- abstention autorisée.

## Limites assumées

- aucun cycle Feature Lab réel n’a été exécuté sur Railway depuis l’environnement d’audit ;
- aucun crédit réel n’a été consommé ;
- les lignes live actuelles peuvent ne pas encore atteindre 30 événements par sport ;
- le Feature Lab pré-enregistre les expériences mais ne promeut ni ne remplace les modèles sportifs ;
- les anciennes observations sans `feature_manifest` restent signalées comme héritées ;
- Alembic et les SHA immuables restent des risques P1.

## Décision finale

V4.6.0 est prête pour un déploiement contrôlé. Le bénéfice immédiat est une interface réellement compacte et une mesure séparée de la fiabilité football/tennis. Le Feature Lab doit rester à zéro crédit et la promotion reste manuelle.
