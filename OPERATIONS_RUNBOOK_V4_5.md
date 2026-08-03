# Runbook opérationnel — V4.5.0

## 1. Déploiement sûr

Déployer web et cron avec `Deploy production` et `verify_browser=true`.

Conserver initialement :

```text
DAILY_ODDS_ENABLED=false
DAILY_ODDS_MAX_CREDITS=0
SHADOW_MODE_ENABLED=false
AUTOMATED_SHADOW_ENABLED=false
HISTORICAL_EVIDENCE_ENABLED=false
```

Vérifier :

```text
/api/ready                         status ready
/api/release                       version 4.5.0
/api/research-lab                  rapport lisible
/api/research-lab/learning         collecting/hold/review_required
```

Le smoke navigateur doit confirmer que la vue simple apparaît avant le chargement expert.

## 2. Activation contrôlée de l’automatisation

Dans Railway :

```text
DAILY_ODDS_ENABLED=true
DAILY_ODDS_MAX_CREDITS=3
SHADOW_MODE_ENABLED=true
AUTOMATED_SHADOW_ENABLED=true
HISTORICAL_EVIDENCE_ENABLED=false
```

Dans GitHub Variables :

```text
AUTOMATED_SHADOW_ENABLED=true
AUTOMATED_SHADOW_MAX_CREDITS=3
AUTOMATED_TENNIS_LIMIT=2
```

Lancer une première fois manuellement :

```text
Actions → Automated shadow learning cycle
’action: cycle
```

Le cycle règle d’abord les événements dus, puis capture les matchs pertinents. L’optimisation s’exécute sans fournisseur.

## 3. Contrôles après cycle

Vérifier dans la vue Apprentissage :

- crédits consommés et plafond ;
- résultats à régler ;
- nombre d’événements football et tennis ;
- état du challenger ;
- prochaine action.

Dans les artefacts GitHub, contrôler :

- `automated-shadow-settlement` ;
- `automated-shadow-capture` ;
- `automated-shadow-challenger`.

Une absence de signal est valide.

## 4. En cas de budget épuisé

Ne pas augmenter le plafond le même jour. La capture doit être refusée. Un règlement sans événement dû reste un no-op à zéro crédit.

## 5. En cas de journée vide

L’automatisation consulte le calendrier gratuit avant le football. Aucun appel football payant ne doit être effectué lorsqu’aucune fixture n’est présente. Le tennis peut rester limité à zéro pendant le diagnostic.

## 6. Promotion manuelle

Lorsque `/api/research-lab/learning` indique `review_required` :

1. télécharger le rapport challenger ;
2. vérifier chaque porte, le holdout et le drawdown ;
3. ouvrir `Promote approved research champion` ;
4. saisir le `RCH-*` exact ;
5. fournir une note de revue ;
6. saisir `PROMOTE_RESEARCH_CHAMPION`.

Cette action enregistre une décision. Elle ne place aucun pari et ne déclenche aucune promotion automatique ultérieure.

## 7. Arrêt immédiat

Refermer :

```text
AUTOMATED_SHADOW_ENABLED=false
DAILY_ODDS_ENABLED=false
DAILY_ODDS_MAX_CREDITS=0
SHADOW_MODE_ENABLED=false
```

Le produit modèle seul et la vue simple continuent de fonctionner.
