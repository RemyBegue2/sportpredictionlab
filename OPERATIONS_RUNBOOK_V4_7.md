# Runbook opérationnel — V4.7.0

## Déploiement

Déployer avec les dépenses fermées :

```text
DAILY_ODDS_ENABLED=false
DAILY_ODDS_MAX_CREDITS=0
SHADOW_MODE_ENABLED=false
AUTOMATED_SHADOW_ENABLED=false
HISTORICAL_EVIDENCE_ENABLED=false
```

Vérifier :

```text
/api/ready                  ready
/api/release                version 4.7.0
/api/challenger-factory     collecting, hold ou review_required
```

## Vérification du cockpit

1. `Aujourd’hui` est le seul panneau visible au démarrage.
2. Les listes affichent au maximum huit cartes.
3. Le nombre d’éléments masqués apparaît sous la liste si nécessaire.
4. Basculer dix fois entre Aujourd’hui, Signaux et Apprentissage.
5. Un seul panneau doit rester actif.
6. Le badge de session doit rester visible sans erreur croissante inexpliquée.
7. Ouvrir le mode expert et vérifier qu’il se charge une seule fois.
8. En cas d’échec partiel, revenir en vue simple puis réessayer.
9. Aucun toast `Interface partiellement chargée` ne doit apparaître.

## Challenger Factory

Depuis GitHub Actions :

```text
Run sport challenger factory
confirmation: RUN_CHALLENGER_FACTORY
```

Le workflow doit confirmer :

```text
provider_credits_consumed = 0
automatic_promotion = false
```

Résultats attendus avec les données livrées :

```text
football.status = hold ou candidate
tennis.status = collecting
```

Le statut tennis `collecting` est normal tant qu’un historique réel multi-surface plus large n’est pas fourni.

## Incident frontend longue session

1. relever le texte de `sessionStatus` ;
2. vérifier la console navigateur ;
3. revenir en vue simple ;
4. actualiser une seule fois la page ;
5. ne pas multiplier les clics de rafraîchissement ;
6. conserver le pare-feu de crédits fermé ;
7. lancer `Verify production` avec le smoke navigateur.

## Incident Challenger Factory

- conserver le champion actuel ;
- ne pas ouvrir le fournisseur ;
- vérifier les hashes dataset ;
- vérifier le nombre de dates distinctes ;
- consulter l’artefact GitHub ;
- relancer uniquement après correction des données ou du code.
