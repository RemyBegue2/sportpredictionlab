# Audit multi-rôles contradictoire — V3.0 The Odds API

Date de revue : 2 août 2026.

## Verdict exécutif

**GO technique** pour connecter localement The Odds API, charger des cotes Winamax France, planifier des snapshots historiques et produire un benchmark reproductible.

**NO-GO statistique** pour publier une liste de paris prétendument rentable avant l'exécution d'un historique réel, multi-saisons et hors temps.

**NO-GO production Internet** sans authentification, rate limiting applicatif, stockage de secrets géré et validation juridique du produit final.

## 1. Product owner

### Demande

Remplacer la saisie manuelle par une liste quotidienne automatiquement alimentée et rendre le produit plus amusant à utiliser.

### Risque signalé

Une automatisation visuelle peut transformer un indicateur expérimental en recommandation perçue comme certaine.

### Décision incorporée

- section web « Flux de cotes » ;
- Winamax détecté directement dans le flux ;
- statuts candidat/abstention conservés ;
- absence de cote ou couverture modèle insuffisante affichée comme motif ;
- aucun stake et aucune validation de coupon.

## 2. Quant spécialisé marchés

### Retour

Le marché ne doit pas être injecté immédiatement comme feature, car cela masquerait la question essentielle : le modèle apporte-t-il quelque chose par rapport au marché ?

### Décision incorporée

Trois adversaires séparés :

1. Winamax dévigué ;
2. consensus médian de bookmakers dévigués ;
3. closing line pré-match.

L'utilisation des mouvements de cote comme feature est repoussée à V3.2, après établissement d'une valeur incrémentale hors échantillon.

## 3. Statisticien et validateur indépendant

### Retour

Un ROI positif sur quelques sélections ne prouve rien. Les seuils d'edge peuvent facilement être sur-ajustés.

### Décision incorporée

- log-loss, Brier, RPS et calibration comme métriques principales ;
- comparaison appariée modèle–marché ;
- bootstrap de la différence de log-loss ;
- seuils figés avant le fold test ;
- fonction de veto exigeant un edge inférieur de confiance positif ;
- interdiction de sélectionner un seuil sur la période finale.

## 4. Trader de cotes

### Retour

La cote brute `1/cote` contient la marge. Une « bonne prédiction » qui ne bat pas la closing line est suspecte.

### Décision incorporée

- dévig par méthode power ;
- fallback proportionnel en cas d'échec numérique ;
- overround stocké ;
- consensus médian pour réduire l'influence d'une cote aberrante ;
- calcul de CLV par ratio de cotes, log-CLV et variation de probabilité implicite.

## 5. Data engineer

### Retour

Les noms d'équipes ne sont pas des identifiants fiables. Le football et le tennis ont des calendriers et identités différents.

### Décision incorporée

- conservation des `event_id` fournisseur ;
- timestamps en UTC ;
- données brutes mises en cache de manière immuable par empreinte de requête ;
- table d'alias EPL initiale ;
- plan séparé `requests` / `targets` pour relier un snapshot à plusieurs événements ;
- clés tennis découvertes via `/v4/sports`, car elles sont propres aux tournois.

### Dette restante

La table d'identités doit devenir une vraie couche de résolution versionnée avant l'extension multi-ligues et WTA.

## 6. FinOps / gestion du quota

### Retour

Une collecte toutes les cinq minutes sur une saison peut consommer le quota sans apporter une information proportionnelle.

### Décision incorporée

- `dry-run` par défaut ;
- estimation du coût avant exécution ;
- plafond `--max-credits` ;
- horizons parcimonieux 24 h, 6 h, 1 h et 10 min ;
- regroupement des événements ayant le même sport et timestamp ;
- six bookmakers dans un groupe inférieur à dix ;
- suivi des en-têtes `x-requests-*` ;
- cache persistant évitant les appels identiques.

## 7. Security engineer

### Retour

La clé est un secret à quota monétaire. Elle ne doit jamais atteindre le JavaScript, les logs applicatifs ou le ZIP.

### Décision incorporée

- variable `THE_ODDS_API_KEY` uniquement côté serveur ;
- hôte API figé pour réduire le risque SSRF ;
- validation des tokens ;
- cache et erreurs sans `apiKey` ;
- endpoint statut ne renvoyant qu'un booléen de configuration ;
- test automatique recherchant la clé dans les fichiers de cache ;
- `.env` ignoré ;
- cache Docker placé dans `/tmp` avec filesystem applicatif en lecture seule.

### Dette restante

Pour Internet : secret manager, authentification, rate limiting par utilisateur, journaux structurés et rotation de clé.

## 8. SRE

### Retour

Le fournisseur peut répondre 429 ou 5xx et les cotes peuvent être temporairement absentes.

### Décision incorporée

- timeout ;
- retries bornés et backoff ;
- prise en compte de `Retry-After` ;
- cache court pour le live et permanent pour l'historique ;
- distinction données en cache / données fraîches ;
- endpoint de santé indiquant seulement si le connecteur est configuré.

## 9. Conformité et licences

### Retour

Le fournisseur autorise les dashboards et outils analytiques, mais interdit la redistribution de ses données comme produit brut autonome. Il demande aussi de garder la clé privée et de vérifier les données auprès de l'opérateur avant d'agir.

### Décision incorporée

- pas d'endpoint de republication massive ;
- interface analytique, pas data feed revendu ;
- avertissement de vérification Winamax ;
- pas d'affiliation ou d'approbation suggérée ;
- pas de stockage d'identifiants Winamax.

## 10. Responsable risque et jeu responsable

### Retour

Une liste quotidienne et des mouvements de cotes peuvent encourager la suractivité.

### Décision incorporée

- aucune taille de mise ;
- aucun martingale/Kelly ;
- aucune notification compulsive intégrée ;
- aucun pari automatique ;
- shortlist vide acceptée ;
- performance affichée avec incertitude et non comme promesse.

## 11. QA / red team

### Scénarios ajoutés

- coût historique avec 1, 10 et 11 bookmakers ;
- rejet de paramètres invalides ;
- clé absente du cache et de l'API statut ;
- normalisation current/historical ;
- marché complet et consensus ;
- alias Manchester City → Man City ;
- regroupement de matchs au même horaire ;
- endpoint live avec fournisseur simulé ;
- estimation historique côté API ;
- métriques appariées et CLV.

## Désaccords et arbitrages

| Désaccord | Arbitrage retenu |
|---|---|
| Produit veut une liste automatique, risque exige une preuve | Liste alimentée, mais candidat seulement après veto statistique |
| Quant veut exploiter les mouvements comme feature | Marché utilisé d'abord comme benchmark externe |
| Trader veut chaque tick, FinOps veut réduire le coût | Quatre horizons pré-match et cache |
| Produit veut toutes les ligues | EPL d'abord, extension après résolution d'identités |
| Tennis veut un flux unique | Découverte dynamique des clés par tournoi |
| Marketing veut montrer le ROI | Log-loss, calibration et CLV avant ROI |
| SRE veut cache persistant, conteneur est read-only | Cache redirigé vers `/tmp` dans Docker |

## Gates avant V3.1 validée

1. Historique d'au moins trois saisons pour le football ciblé.
2. Plusieurs folds expanding-window sans chevauchement temporel.
3. Couverture Winamax et consensus documentée par période.
4. Différence modèle–marché en log-loss avec intervalle de confiance.
5. CLV positive pour une règle de sélection figée.
6. Taux d'appariement des événements supérieur à 99 % après revue des exceptions.
7. Aucun changement de seuil après observation du fold final.
8. Rapport séparé ATP et WTA avec timestamps de match suffisamment précis.

## Conclusion

La clé historique change réellement la qualité du projet : elle permet enfin de juger le modèle contre le prix auquel une décision aurait été possible. Elle ne transforme toutefois pas automatiquement le modèle en avantage exploitable. La V3.0 construit la chaîne de preuve ; la V3.1 devra exécuter cette preuve avec le quota de l'utilisateur.
