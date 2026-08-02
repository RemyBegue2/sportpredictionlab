# Audit multi-rôles contradictoire — Sports Prediction Lab V2.1

## Verdict exécutif

**Décision globale : GO pour démonstration locale et recherche ; NO-GO pour production publique, usage commercial tennis, conseil de mise ou automatisation financière.**

La V2 initiale fonctionnait, mais l’audit a identifié une fuite temporelle subtile : lorsque plusieurs événements partageaient la même date, les résultats des premières lignes pouvaient influencer les suivantes. Le problème était particulièrement sérieux pour l’archive ATP, où `tourney_date` correspond généralement au début du tournoi et non à l’heure réelle de chaque match. La V2.1 traite désormais toutes les lignes de même horodatage comme un lot simultané, aligne les splits et les folds sur les frontières temporelles, et interdit les rétro-prédictions dans l’API.

Le produit est nettement plus honnête : le snapshot tennis ne contient que deux dates de tournoi, donc aucune calibration ou évaluation valable n’est publiée. L’application sert un **Elo symétrique non calibré** pour démontrer le parcours produit, sans revendiquer une performance.

## Tableau de décision

| Usage | Décision | Conditions |
|---|---|---|
| Démo locale / portfolio | **GO** | Conserver les avertissements et le snapshot comme smoke test |
| Recherche interne | **GO conditionnel** | Télécharger plusieurs saisons, exécuter le backtest verrouillé, documenter les sources |
| Pilote public sans enjeu financier | **NO-GO actuellement** | Authentification, rate limiting, monitoring, politique de réentraînement et test navigateur requis |
| Produit commercial tennis | **NO-GO** | Autorisation/licence commerciale obligatoire |
| Recommandation ou exécution de paris | **NO-GO** | Validation statistique, juridique et risque indépendante ; aucun module de mise livré |

## Résultats vérifiés après corrections

### Qualité logicielle

- Tests automatisés : **17/17 réussis**.
- Couverture globale : **88 %**.
- Couverture du module de backtest : **92 %**.
- Routes vérifiées : accueil, santé, catalogue, métriques, documentation et deux prédictions.
- Contrôles ajoutés : anti-fuite même horodatage, rétro-prédiction, intégrité des artefacts, données tennis incomplètes, codes de ligue malveillants, backtests par lots.

### Football — smoke test réel, non promotionnel

Entraînement interne sur 90 matchs EPL 2023-24 :

| Mesure | Valeur |
|---|---:|
| Test interne | 20 matchs |
| Log-loss | 0.9399 |
| Baseline naïve | 1.1159 |
| Accuracy | 60.0% |
| ECE | 0.0781 |
| Poids du classifieur ML | 0.00 |
| Dixon–Coles rho | -0.150 |

Backtest externe corrigé, 30 prédictions groupées par date :

| Mesure | Valeur |
|---|---:|
| Log-loss | 0.9872 |
| Baseline naïve | 1.0740 |
| Écart moyen | -0.0868 |
| IC bootstrap en blocs | [-0.1094 ; -0.0176] |
| Accuracy | 53.3% |
| ECE | 0.1767 |

L’intervalle est favorable sur cet extrait, mais **30 observations, une seule ligue, une courte période et un seul fold ne suffisent pas**. Le paramètre Dixon–Coles atteint la borne de recherche et la température atteint presque sa borne supérieure ; ce sont des signaux d’instabilité sur petit échantillon, pas des preuves de qualité.

### Tennis — décision d’abstention statistique

- Snapshot : 32 matchs, mais seulement **deux horodatages de tournoi**.
- Évaluation externe : **non calculée**, car un split fuite-safe est impossible.
- Mode de l’application : **Elo global + surface, symétrique, non calibré**.
- Walkovers, défauts et abandons : exclus du pipeline réel par défaut.

## Revue par rôles

### 1. Product owner

**Retour.** Le site doit rester immédiatement démontrable, mais ne doit pas transformer un échantillon invalide en argument de performance.

**Décisions intégrées.** FastAPI devient l’application canonique ; Streamlit reste optionnel. Le wording tennis indique explicitement « Elo non calibré ». Les dates antérieures au cutoff sont refusées. Le tableau de scores football, qui affichait des champs inexistants, a été corrigé.

**Risque restant.** Aucun test navigateur visuel ou test d’accessibilité automatisé.

### 2. Data engineer

**Retour.** La provenance doit être vérifiable et les entrées sales ne doivent pas contaminer les états Elo.

**Décisions intégrées.** Manifestes SHA-256, cache, retries, écritures atomiques, limites de taille, nettoyage des noms, suppression des doublons, validation des buts et des codes de ligue, colonne explicite de provenance des cotes.

**Risque restant.** Absence d’identifiants canoniques d’équipes/joueurs et URLs de sources encore mutables. Il faut pinner une révision ou archiver les fichiers bruts.

### 3. Auditeur anti-fuite

**Retour.** « Calculé avant le résultat courant » ne suffit pas lorsque plusieurs lignes partagent le même timestamp.

**Décisions intégrées.** Les états Elo, formes et moyennes ne sont mis à jour qu’après tout le lot de même date. Les splits train/calibration/test et les folds externes ne coupent plus un timestamp. Les résultats d’un jour ou tournoi de test ne sont révélés qu’après toutes ses prédictions.

**Risque restant.** Les sources ne fournissent pas toujours `kickoff_at`, `match_start_at` ou `observed_at`. Le traitement par lot est conservateur mais ne remplace pas un vrai horodatage.

### 4. Statisticien football

**Retour.** La baseline Poisson–Dixon-Coles doit rester prioritaire et l’accuracy ne doit pas guider la promotion.

**Décisions intégrées.** Log-loss, Brier, RPS et ECE restent principales. Le classifieur ML est rejeté sur le snapshot : poids final **0**. Le backtest externe compare une baseline explicite.

**Risque restant.** Pas de modèle hiérarchique équipe/ligue/saison, pas de xG pré-match, effectifs ou entraîneurs. Les bornes de calibration atteintes imposent davantage de données et une régularisation du rho.

### 5. Analyste tennis

**Retour.** `tourney_date` est une date de tournoi, pas un ordre fiable des matchs ; abandons et walkovers ne doivent pas être traités comme des matchs complétés ordinaires.

**Décisions intégrées.** Un tournoi partageant le même timestamp est traité comme simultané. Les rangs du match peuvent être fournis dans les fixtures du backtest. Walkovers, défauts et retraites sont filtrés par défaut. Le snapshot insuffisant déclenche le mode Elo-only.

**Risque restant.** Manquent service/retour pré-match, indoor, altitude, voyage, fatigue, blessures et date exacte. Les règles de règlement d’un abandon diffèrent aussi selon le marché évalué.

### 6. ML engineer

**Retour.** Un modèle complexe ne doit être conservé que s’il démontre un gain stable hors temps.

**Décisions intégrées.** Calibration séparée, fallback à la baseline, symétrie tennis, métriques probabilistes et backtest externe. Le snapshot ne force jamais CatBoost dans la sortie finale.

**Risque restant.** Le poids du mélange et la température sont encore estimés sur une seule fenêtre interne. La prochaine étape doit être une validation imbriquée ou du cross-fitting. Les artefacts de `fit()` correspondent au modèle entraîné sur la partie train interne, pas à un refit final sur toutes les données disponibles.

### 7. QA engineer

**Retour.** Les tests smoke n’exerçaient presque pas le protocole de backtest et ne pouvaient pas détecter le bug UI des scores.

**Décisions intégrées.** Tests dédiés aux lots temporels football/tennis, à l’intégrité, aux rétro-prédictions, aux téléchargements et aux folds. La couverture du backtest passe à 92 %.

**Risque restant.** Pas de Playwright/Cypress, de test de charge, de test Docker exécuté dans cet environnement ni de matrice multi-version Python.

### 8. Security engineer

**Retour.** Joblib/pickle est exécutable au chargement ; l’API publique manque de durcissement et les paramètres de chemin doivent être contrôlés.

**Décisions intégrées.** Vérification SHA-256 avant chargement, CSP, `nosniff`, anti-framing, politique de permissions, code de ligue validé, conteneur non-root, filesystem read-only et `no-new-privileges`.

**Risque restant.** Un attaquant capable de modifier à la fois le manifeste et l’artefact peut contourner le hash. Joblib doit être remplacé par un format plus sûr ou signé. Pas d’authentification, rate limiting ou gestion des secrets : déploiement Internet interdit en l’état.

### 9. SRE / MLOps

**Retour.** Le service doit signaler son état et être reproductible sans dépendre d’un volume qui masque les artefacts intégrés.

**Décisions intégrées.** Endpoint de santé, manifeste des modèles, image non-root, dépendances web séparées, container read-only et suppression du volume d’artefacts fragile.

**Risque restant.** Pas de métriques Prometheus, traces, logs structurés, registre de modèles, rollback, surveillance de dérive ou SLA de fraîcheur.

### 10. Juriste données

**Retour.** Données accessibles publiquement ne signifie pas usage commercial libre.

**Décisions intégrées.** Les notes de licence sont visibles et le produit bloque explicitement toute conclusion commerciale tennis. Un fichier `LICENSE_STATUS.md` signale aussi que la licence du code du projet n’a pas encore été choisie.

**Risque restant.** Validation juridique formelle nécessaire pour la redistribution, les cotes et tout usage commercial.

### 11. Risk manager / red team

**Retour.** Une bonne probabilité ne garantit ni avantage économique ni rentabilité. Les petits échantillons produisent facilement de fausses certitudes.

**Décisions intégrées.** Aucun staking, aucun « pari sûr », cotes isolées en baseline, avertissements visibles et décision de non-évaluation tennis.

**Risque restant.** Le produit n’a pas encore de mécanisme automatique d’abstention pour entité inconnue, données trop anciennes, dérive ou forte incertitude ; l’API refuse seulement les entités absentes du snapshot.

## Désaccords arbitrés

| Désaccord | Arbitrage retenu |
|---|---|
| Produit : « il faut une probabilité tennis visible » / Statisticien : « deux dates ne permettent aucune calibration » | Afficher uniquement un Elo non calibré et publier `n_test = 0` |
| ML : « utiliser CatBoost » / Validateur : « pas sans gain démontré » | Poids ML à zéro lorsque le garde-fou échoue |
| Data : « utiliser les matchs précédents du tournoi » / Anti-fuite : « l’ordre réel est inconnu » | Tout le même `tourney_date` est simultané |
| SRE : « Joblib est simple » / Sécurité : « pickle est dangereux » | Hash et canal de confiance maintenant ; migration de format obligatoire avant production |
| Marketing : « l’IC football est favorable » / Risque : « 30 matchs ne suffisent pas » | Résultat présenté comme smoke test, jamais comme validation |

## Bloquants avant V3

1. Exécuter un benchmark multi-saisons et multi-ligues avec folds groupés par timestamp.
2. Obtenir des dates/heures réelles et des champs `observed_at` pour toute variable externe.
3. Remplacer la calibration unique par validation imbriquée/cross-fitting et définir un refit final.
4. Sécuriser les droits des données tennis et choisir une licence pour le code.
5. Ajouter abstention, monitoring de dérive, fraîcheur, logs et registre de modèles.
6. Ajouter tests navigateur, accessibilité, charge et construction Docker en CI.
7. Remplacer ou signer les artefacts Joblib.

## Conclusion

La V2.1 est **plus crédible parce qu’elle publie moins de certitudes**. Les corrections empêchent une classe réelle de fuite temporelle, ferment plusieurs défauts produit et sécurité, et rendent le pipeline testable. Le résultat football mérite un benchmark complet ; le tennis mérite d’abord des données temporelles suffisantes. Toute promotion avant ces étapes serait prématurée.
