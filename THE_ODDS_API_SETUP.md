# Configuration The Odds API

## Secret

Utiliser exclusivement la variable d'environnement `THE_ODDS_API_KEY`. Ne jamais :

- l'écrire dans `static/app.js` ;
- l'envoyer dans une requête depuis le navigateur ;
- la committer dans Git ;
- la copier dans un rapport ou une capture d'écran ;
- partager le cache sans contrôle.

## Bookmakers V3

- `winamax_fr`
- `betclic_fr`
- `unibet_fr`
- `pmu_fr`
- `netbet_fr`
- `pinnacle`

Les six sont demandés dans un même appel. Le consensus exclut Winamax afin de comparer l'opérateur à un marché externe.

## Coût

Le client applique la règle documentée :

```text
current cost = snapshots × markets × groupes de 10 bookmakers
historical cost = 10 × snapshots × markets × groupes de 10 bookmakers
```

Exemple : 120 timestamps historiques, un marché et six bookmakers = 1 200 crédits estimés.

## Cache

L'empreinte dépend du chemin et des paramètres hors clé. Deux appels identiques réutilisent le même fichier. L'historique n'expire pas ; le live expire après 90 secondes.

## Commandes de contrôle

```bash
python scripts/odds_api_probe.py
curl http://localhost:8000/api/odds/status
```

Le statut ne révèle pas la clé.

## Données historiques

Les snapshots doivent être collectés à des horizons définis avant le match. La clôture retenue par défaut est 10 minutes avant le coup d'envoi. Les événements partageant le même timestamp sont regroupés en une seule requête par sport.

## Conditions d'utilisation

L'application affiche des analyses dérivées. Elle ne doit pas devenir une API de redistribution de cotes brutes. Toute utilisation publique ou commerciale doit vérifier les conditions du fournisseur et les règles locales applicables.
