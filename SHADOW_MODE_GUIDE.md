# Guide pratique — V3.3 Shadow Mode

## À quoi sert le shadow mode ?

Il enregistre automatiquement ce que le système aurait dit avant un match, puis attend le résultat. Il ne place aucun pari.

Une observation contient le match, le modèle, la probabilité, la cote Winamax, l’heure de la cote, l’heure de création et le jalon temporel.

## Jalous enregistrés

- `t-24h` : entre 6 h et 24 h avant le match ;
- `t-6h` : entre 1 h et 6 h ;
- `t-1h` : entre 20 min et 1 h ;
- `pre-close` : dans les 20 dernières minutes.

Une seule ligne est conservée par match, version de modèle et jalon.

## Installation sur Railway

Le service web existant utilise `railway.toml`.

Crée un deuxième service depuis le même dépôt :

1. nomme-le `shadow-cron` ;
2. sélectionne le même dépôt et la même branche ;
3. dans Settings, indique `/railway.cron.toml` comme chemin de configuration ;
4. référence la même variable `DATABASE_URL` ;
5. ajoute `THE_ODDS_API_KEY` ;
6. ajoute les variables ci-dessous ;
7. déploie et consulte les logs du premier cycle.

Variables minimales :

```text
APP_ENV=production
DATABASE_URL=${{Postgres.DATABASE_URL}}
THE_ODDS_API_KEY=...
MODEL_VERSION=3.3.0
ODDS_SYNC_SPORTS=soccer_epl
SHADOW_MODE_ENABLED=true
SHADOW_QUOTA_FLOOR=100
MODEL_MAX_AGE_DAYS=365
```

Le cron n’a pas besoin d’un domaine public.

## Premier contrôle

Après un cycle, ouvre dans l’application la section **Shadow**. Elle doit afficher :

- l’heure du dernier cycle ;
- son statut ;
- les événements vus ;
- les prédictions créées ou réutilisées ;
- le quota restant.

Endpoint privé :

```text
/api/shadow/summary
```

## Statuts de cycle

- `ok` : cycle terminé ;
- `partial_failure` : au moins une partie a fonctionné ;
- `failed` : aucune partie utile n’a fonctionné ;
- `quota_guard` : arrêt volontaire sous le plancher de quota.

## Pourquoi le modèle est marqué degraded ?

Le modèle football embarqué utilise des données s’arrêtant au 23 octobre 2023. Pour des matchs en 2026, il est trop ancien. La V3.3 montre encore ses probabilités à des fins de mesure, mais bloque toute shortlist opérationnelle.

## Résultats

Le cycle demande uniquement les résultats des événements arrivés à échéance. Les prédictions football passent alors de `open` à `settled` et reçoivent leurs métriques.

## Interprétation

- moins de 100 résultats : aucune conclusion ;
- 100 à 299 : exploration ;
- 300 à 499 : signal préliminaire ;
- 500 et plus : début d’une évaluation, pas preuve définitive.

Le résultat fictif en unités ne constitue ni un rendement attendu ni une recommandation de mise.
