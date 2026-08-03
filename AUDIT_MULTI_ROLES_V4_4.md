# Audit multi-rôles — Sports Prediction Lab V4.4.0

## Verdict consolidé

- **Produit quotidien football + tennis : GO contrôlé.**
- **Signaux de marché : GO en mode shadow uniquement.**
- **Simulations de bankroll : GO comme métriques de recherche, jamais comme conseil de mise.**
- **Optimisation : GO sur validation chronologique et holdout, NO-GO sur ROI in-sample.**
- **Placement automatique, connexion bookmaker et mise réelle : interdits.**

## Product Owner

La demande est ramenée à un écran simple : matchs de football et de tennis du jour, probabilités, éventuel signal expérimental, simulations de bankroll et état d'entraînement. Le chargement de cette vue lit uniquement PostgreSQL et ne déclenche aucun appel fournisseur.

## Quant / Statisticien

Optimiser directement un modèle prédictif sur le ROI historique créerait un sur-ajustement. La V4.4 sépare donc :

1. les modèles sportifs, entraînés pour estimer des probabilités ;
2. une politique de sélection déterministe, choisie sur plusieurs blocs chronologiques ;
3. un méta-modèle logistique de qualité du signal, sélectionné sur validation chronologique et évalué sur les 20 % de dates finales jamais vues ;
4. des simulations de bankroll après règlement des résultats.

La politique teste 144 combinaisons bornées d'edge, d'EV robuste, de cote maximale et de nombre maximal de signaux par jour. Son score pénalise l'instabilité, le ROI négatif et le drawdown. Un statut `candidate` ne constitue pas une preuve de rentabilité.

## Ingénieur ML

Le méta-modèle utilise une seule décision par événement afin de ne pas compter les issues mutuellement exclusives comme observations indépendantes. Il emploie six caractéristiques pré-match : probabilité du modèle, probabilité du marché, edge, EV robuste, log-cote et indicateur tennis.

Il faut au moins 60 événements réglés au total. Un modèle de base ayant abstenu, notamment le tennis Elo non calibré, ne peut être réhabilité que si le méta-modèle est candidat et dispose d'au moins 30 événements réglés pour le même sport.

Les paramètres du méta-modèle sont stockés sous une forme portable — normalisation, coefficients et intercept — plutôt que dans un artefact arbitraire chargé par le serveur.

## Data Engineer

Les observations sont immuables et rattachées à l'identifiant fournisseur, au sport, à l'heure de début, au snapshot de marché et au résultat. Football et tennis sont réglés dans le même journal shadow, mais les statistiques conservent leur sport d'origine.

## FinOps

La capture live est manuelle et plafonnée. Elle exige simultanément :

- `DAILY_ODDS_ENABLED=true` ;
- `DAILY_ODDS_MAX_CREDITS>=1` ;
- `SHADOW_MODE_ENABLED=true` ;
- la confirmation `CAPTURE_DAILY_MARKET`.

Cette dernière porte garantit que chaque appel payé crée une preuve réglable. Le dashboard n'appelle jamais le fournisseur. L'entraînement hebdomadaire du ROI ne consomme aucun crédit.

## SRE

Trois workflows séparés sont fournis : capture, règlement et optimisation. Les deux premiers sont manuels et plafonnés ; le troisième est sans fournisseur. Le smoke test Chromium exige le rendu du laboratoire ROI et échoue en présence d'une erreur JavaScript ou d'une interface partiellement chargée.

## QA

La suite contient 219 tests. Les régressions V4.4 couvrent notamment :

- règlement tennis ;
- extraction football + tennis ;
- politiques chronologiques et holdout ;
- méta-modèle réel et portable ;
- une seule ligne d'entraînement par événement ;
- simulations de bankroll multiples ;
- blocage du fournisseur lorsque le pare-feu ou le shadow sont fermés ;
- plafond de crédits ;
- capture dual-sport ;
- règlement dual-sport ;
- possibilité conditionnelle de réhabiliter un signal tennis après preuve spécifique au sport ;
- rendu obligatoire du laboratoire ROI dans Chromium.

## Sécurité

Les clés restent côté serveur. Les clés tennis fournies manuellement sont limitées au format `tennis_*`. Les appels payants passent uniquement par des endpoints POST authentifiés et protégés par CSRF. Aucun montant de mise, ordre de pari ou identifiant de compte bookmaker n'est traité.

## Usage responsable

Le libellé « pari intéressant » correspond uniquement à un `SHADOW_SIGNAL` expérimental. Il ne s'agit ni d'une garantie, ni d'une instruction, ni d'une recommandation personnalisée. Les stratégies flat et Kelly sont des simulations rétrospectives sur bankroll fictive.

## Risques résiduels

- le modèle tennis embarqué reste Elo non calibré tant que la preuve spécifique au tennis est insuffisante ;
- aucun historique live réglé V4.4 n'existe encore dans l'environnement de préparation ;
- un holdout positif sur un petit nombre de signaux ne prouve pas une rentabilité future ;
- les cotes Winamax peuvent être absentes du flux fournisseur ;
- les actions GitHub restent majoritairement référencées par tags majeurs ;
- Alembic reste à introduire avant des migrations complexes.

## Décision finale

V4.4.0 est prête pour un déploiement contrôlé. Commencer avec un plafond de trois crédits, capturer uniquement les matchs du jour, régler les résultats, puis laisser le système accumuler la preuve. Ne modifier aucun seuil après observation des résultats sans créer une nouvelle version de politique.
