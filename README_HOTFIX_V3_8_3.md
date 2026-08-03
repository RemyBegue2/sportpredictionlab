# Hotfix V3.8.3 — contrat The Odds API et plafond global

## Cause exacte

Le endpoint `GET /v4/historical/sports/{sport}/events` accepte le paramètre historique `date`.
La V3.8.2 lui envoyait aussi `dateFormat`, `commenceTimeFrom` et `commenceTimeTo`.
Le fournisseur rejetait donc la requête avec HTTP 422.

La V3.8.3 :

- envoie uniquement `date` au endpoint historique des événements ;
- filtre les heures de début localement après réception ;
- affiche désormais le code et le message exacts renvoyés par le fournisseur ;
- évite les snapshots futurs ;
- compte les crédits éventuellement consommés pendant la découverte ;
- déduit ces crédits du plafond global ;
- désactive la closing line pour ce premier lot T-1 h ;
- réduit automatiquement le nombre d'événements si 30 événements dépassent le plafond ;
- conserve Winamax, Betclic, Unibet, PMU et Pinnacle ;
- refuse de dépasser le plafond demandé.

## Installation sans Python local

Décompresser le ZIP à la racine du dépôt GitHub et remplacer les fichiers existants.
Créer le commit :

`Fix historical provider contract and global credit cap v3.8.3`

Puis lancer une nouvelle estimation :

`Actions → Estimate historical sample → Run workflow`

L'ancien identifiant `REQ-...` n'est plus valable, car le plan passe du schéma 1.1 au schéma 1.2.
Recopier le nouveau `REQ-...`, puis lancer :

`Actions → Run historical sample → Run workflow`

Utiliser exactement les mêmes dates et plafonds que dans l'estimation.

## Résultat attendu

L'étape `Discover provider events within the global credit cap` ne doit plus produire
`The Odds API rejected one or more request parameters`.

L'estimation indique maintenant :

- coût maximal demandé avant adaptation ;
- plafond global réel ;
- nombre maximal de snapshots uniques dans ce plafond ;
- réduction automatique de l'échantillon si nécessaire.

Avec 30 événements, T-1 h, 5 bookmakers et 120 crédits, le coût maximal demandé est 300 crédits.
L'exécution sélectionne donc au maximum les événements dont les snapshots uniques tiennent dans 120 crédits.

## Erreurs fournisseur désormais explicites

Une erreur restante affichera son code réel, par exemple :

- `HISTORICAL_UNAVAILABLE_ON_FREE_USAGE_PLAN` : l'abonnement ne donne pas accès à l'historique ;
- `OUT_OF_USAGE_CREDITS` : quota mensuel épuisé ;
- `INVALID_HISTORICAL_TIMESTAMP` : timestamp refusé ;
- `UNKNOWN_SPORT` : clé de sport indisponible.

Ces erreurs ne peuvent pas être corrigées par un changement de code lorsque l'abonnement ou le quota est en cause.

## Validation

- 126 tests réussis ;
- compilation Python réussie ;
- 9 workflows YAML valides ;
- test de contrat : seul `date` est envoyé au endpoint historique des événements ;
- test budgétaire : 20 événements demandés avec 120 crédits donnent 12 événements sélectionnés et 120 crédits estimés ;
- aucune clé API n'est écrite dans les erreurs ou le cache.
