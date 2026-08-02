# Audit multi-rôles contradictoire — V2.2 Winamax

## Verdict exécutif

**GO pour une analyse locale et manuelle des cotes. NO-GO pour toute automatisation, promesse de gains ou publication de “tips” présentés comme validés.**

La demande d'une liste de paris du jour a révélé un risque produit classique : transformer une prédiction en recommandation alors que la cote, sa fraîcheur, la marge du bookmaker et l'incertitude du modèle ne sont pas maîtrisées. La V2.2 répond en ajoutant un comparateur de marché conservateur et un mécanisme d'abstention explicite.

## Résultat du jour — 2 août 2026

Deux finales ont été vérifiées dans les calendriers et actualités officielles :

1. ATP Washington : Taylor Fritz – Rafael Jodar.
2. WTA Washington : Jessica Pegula – Alexandra Eala.

**Shortlist finale : zéro candidat recherche.**

Raisons :

- Rafael Jodar est absent du snapshot ATP embarqué ;
- aucun modèle WTA n'existe dans cette version ;
- le modèle ATP embarqué est non calibré ;
- aucune cote Winamax horodatée n'a été récupérée de manière vérifiable.

Cette sortie vide est jugée correcte par le statisticien, le risk manager et la red team. Inventer une cote ou extrapoler une probabilité aurait été un défaut plus grave que ne rien proposer.

## Rôles et retours intégrés

### 1. Utilisateur / product owner

**Besoin.** Voir rapidement les événements du jour et pouvoir confronter le modèle aux cotes réellement disponibles sur Winamax.

**Décisions.** Nouvelle section “Paris du jour”, cartes de statut, champs de cotes intégrés aux formulaires football et tennis, résultat lisible dans le même écran.

### 2. Spécialiste Winamax

**Retour.** Les cotes changent entre la sélection et la validation. L'application ne doit ni se connecter au compte ni placer automatiquement un pari.

**Décisions.** Saisie manuelle, horodatage du relevé, bookmaker affiché, aucune authentification Winamax et aucun endpoint de placement de pari. Le règlement public Winamax interdit les robots ou logiciels permettant des prises de paris automatiques.

### 3. Trader de cotes

**Retour.** Comparer `p modèle` à `1/cote` sur une seule sélection surestime l'edge à cause de la marge du bookmaker.

**Décisions.** Marché complet obligatoire. Le moteur normalise les probabilités implicites, publie l'overround, la fair odd, l'edge face au marché dévigé et l'EV.

### 4. Statisticien

**Retour.** Une probabilité ponctuelle sans intervalle est trop agressive. L'EV doit survivre à une baisse prudente de la probabilité modèle.

**Décisions.** Haircut de 5 points en football et 6 points en tennis avant calcul de l'EV robuste. Seuils : edge minimal 3 points et EV robuste minimale 2 %. Un modèle non calibré force l'abstention.

### 5. Risk manager

**Retour.** Le système ne doit pas optimiser la taille de mise sur un snapshot aussi petit.

**Décisions.** Aucun Kelly, aucune mise recommandée, aucun combiné, aucune projection de rendement du portefeuille. Les statuts sont “candidat recherche”, “surveillance”, “à actualiser” et “abstention”.

### 6. Red team

**Retour.** L'interface pourrait pousser l'utilisateur à remplir des cotes partielles ou anciennes pour obtenir artificiellement un signal.

**Décisions.** Toutes les cotes d'un marché sont requises ensemble. Une heure absente ou une cote âgée de plus de 60 minutes empêche le statut candidat. Un overround supérieur à 18 % déclenche un veto.

### 7. Juriste / conformité

**Retour.** Winamax est un opérateur agréé en France, mais cela ne donne aucun droit de réutiliser automatiquement son interface, ses données ou son compte. Les compétitions ouvertes aux paris sont encadrées par la liste sport de l'ANJ.

**Décisions.** Pas de scraping authentifié, pas d'intégration de compte, pas d'exécution. Les sources quotidiennes servent à identifier les matchs, tandis que les cotes doivent être saisies par l'utilisateur.

### 8. Data engineer

**Retour.** Une “cote actuelle” sans `observed_at` n'est pas une donnée auditable.

**Décisions.** Champ ISO-8601, calcul de l'âge en minutes et source bookmaker explicite. Le fichier quotidien conserve date, timezone, heure de génération, sources et motifs d'abstention.

### 9. QA

**Retour.** Les nouveaux calculs doivent être testés indépendamment du modèle et via l'API.

**Décisions.** Tests du dévigage, de la somme des probabilités, du veto non calibré, des entrées invalides, du marché incomplet, du endpoint quotidien et du retour de l'analyse football.

## Contrôles implémentés

- validation des cotes décimales entre 1,01 et 1000 ;
- probabilités strictement comprises entre 0 et 1 et somme égale à 1 ;
- retrait de la marge pour marchés 2-way et 3-way ;
- calcul de l'âge de la cote ;
- statut non candidat sans horodatage ;
- veto sur modèle non calibré ;
- absence totale de stake sizing et d'exécution ;
- validation stricte de la date du fichier quotidien contre la traversée de chemin.

## Tests et couverture

- **24/24 tests réussis** ;
- couverture globale : **88 %** ;
- `backtest.py` : **92 %** ;
- `betting.py` : **88 %** ;
- `webapp.py` : **85 %**.

## Désaccords arbitrés

| Désaccord | Arbitrage |
|---|---|
| Produit veut une liste quotidienne / Statisticien refuse des sélections non couvertes | Afficher les événements et leurs motifs d'abstention |
| Trader veut classer les EV positives / Risk manager exige de l'incertitude | Classement sur EV robuste, jamais sur EV brute seule |
| Utilisateur veut Winamax / Conformité refuse une intégration de compte | Cotes manuelles horodatées, aucun login ni pari automatique |
| Marketing voudrait une sélection par jour / Red team accepte zéro sélection | Zéro candidat est un résultat valide et visible |
| Tennis veut profiter de l'Elo / Auditeur rappelle l'absence de calibration | Toute analyse de cote tennis reste “abstention” dans le snapshot |

## Bloquants avant une V3 réellement utile au quotidien

1. Actualiser chaque jour les historiques ATP et football avec provenance pannée.
2. Construire et calibrer un modèle WTA distinct.
3. Obtenir une source de cotes autorisée, documentée et horodatée, ou conserver l'import manuel.
4. Backtester la règle de sélection complète, y compris clôture de cote, slippage et paris non disponibles.
5. Mesurer le closing-line value sans l'utiliser comme substitut au profit réel.
6. Ajouter tests navigateur, accessibilité et suivi des erreurs de saisie.
7. Définir une politique de fraîcheur et d'expiration des modèles.

## Conclusion

La V2.2 ne cherche pas à fabriquer plus de paris ; elle cherche à éliminer les mauvais signaux. Pour le 2 août 2026, le bon résultat est une revue de deux finales et aucune sélection validée. C'est précisément le comportement attendu d'un outil honnête lorsque le modèle et les cotes disponibles ne suffisent pas.
