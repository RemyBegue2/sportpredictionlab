# Audit multi-rôles — Sports Prediction Lab V3.4

## Verdict

La V3.4 est un **GO technique** pour une application privée Railway et un **NO-GO sportif** tant qu'un nouveau modèle n'a pas été reconstruit puis validé. Elle corrige deux faiblesses de la V3.3 : les cycles à zéro étaient opaques et le modèle football actif était entraîné sur un petit snapshot arrêté au 23 octobre 2023.

## Décisions contradictoires intégrées

### Product owner

Le message « aucune prédiction » ne permettait aucune action. Le dernier cycle expose désormais un entonnoir : événements fournisseur, événements examinés, rencontres commencées, hors jalons, identités non couvertes, Winamax absent, marchés incomplets, veto du modèle, absence d'edge, créations et réutilisations.

### Data engineer

La reconstruction est reproductible à partir de cinq fichiers de saison Premier League, normalisés vers un schéma unique. Les lignes invalides, scores négatifs et doublons sont éliminés. Le dataset exporté reçoit une empreinte SHA-256.

### Auditeur anti-fuite

Les caractéristiques restent calculées séquentiellement et les rencontres partageant le même timestamp sont traitées en lot. Le nouveau modèle n'écrase aucune ancienne prédiction. Une promotion produit un nouvel artefact et un rapport traçable.

### Statisticien

Le candidat doit contenir au moins 1 500 matchs, au moins 250 observations dans le test chronologique, battre la baseline naïve et conserver une ECE inférieure ou égale à 0,15. Ces seuils constituent un filtre de promotion, pas une preuve de rentabilité.

### Ingénieur ML

La V3.4 réutilise volontairement l'architecture Poisson/Dixon–Coles + CatBoost existante afin de comparer l'effet des données avant de modifier l'algorithme. Le modèle candidat est enregistré séparément sous `football_model_candidate.joblib`.

### Quant et trader de cotes

Le marché reste une baseline externe. Une amélioration face à la fréquence naïve ne suffit pas : les observations shadow devront ensuite être comparées à Winamax et au consensus. Une cote manquante ou incomplète reste un motif d'abstention.

### SRE

Un verrou consultatif PostgreSQL empêche deux cycles shadow simultanés. Les statuts deviennent explicites : `success`, `partial`, `skipped_quota`, `skipped_locked` ou `provider_error`. Le cycle enregistre durée, quota avant/après et diagnostic détaillé.

### FinOps

Le plancher de quota reste bloquant. Le pipeline de reconstruction football utilise des données publiques gratuites et n'appelle pas The Odds API.

### Sécurité

Les artefacts actifs continuent d'être vérifiés par manifeste. Le Dockerfile conserve les artefacts préconstruits au lieu de réentraîner silencieusement le vieux snapshot pendant chaque build. La reconstruction automatisée ne requiert aucun secret.

### QA

La migration SQLite/PostgreSQL, les diagnostics, le verrou, la normalisation des saisons, les politiques de promotion, les endpoints et le frontend sont testés. Les appels réseau réels et le build Docker restent à valider dans GitHub Actions/Railway.

### Jeu responsable

Le pipeline peut conclure qu'aucun modèle n'est promouvable. Aucune taille de mise, aucun objectif de rendement et aucun pari automatique ne sont ajoutés.

## Risques restant ouverts

1. Le nouvel entraînement réel doit être exécuté dans GitHub Actions, car l'environnement de construction de cette livraison n'avait pas d'accès réseau sortant utilisable.
2. La source multi-saisons ne fournit pas systématiquement une heure exacte de coup d'envoi ; les matchs d'une même date restent donc traités en lot conservateur.
3. Les données d'effectifs, blessures et changements d'entraîneur ne sont pas encore intégrées.
4. Le candidat devra encore accumuler des observations shadow avant toute promotion opérationnelle.
5. Un test de restauration PostgreSQL et un smoke test réel du verrou sur Railway restent nécessaires.

## Décision finale

- **GO** : déployer la V3.4, lire les diagnostics de cycles et exécuter le workflow de reconstruction.
- **GO conditionnel** : activer le nouveau modèle uniquement si toutes les règles de promotion sont vertes.
- **NO-GO** : présenter le modèle comme rentable ou automatiser des prises de paris.
