# Upgrade V4.3.0 → V4.4.0

## Nouveautés

- vue simple football + tennis du jour ;
- signaux de marché expérimentaux ;
- capture et règlement live plafonnés ;
- simulations de bankroll 100, 500 et 1 000 ;
- stratégies flat 1 %, flat 2 % et quart de Kelly plafonné à 2 % ;
- politique ROI optimisée chronologiquement ;
- méta-modèle logistique avec validation et holdout ;
- preuve spécifique au sport avant réhabilitation d'une abstention tennis ;
- aucun appel fournisseur depuis le dashboard.

## Variables

Le mode sûr reste :

```text
DAILY_ODDS_ENABLED=false
DAILY_ODDS_MAX_CREDITS=0
SHADOW_MODE_ENABLED=false
HISTORICAL_EVIDENCE_ENABLED=false
DAILY_TENNIS_MAX_TOURNAMENTS=2
DAILY_TENNIS_SPORT_KEYS=
```

Pour une capture manuelle limitée, activer temporairement les trois premières variables conformément au runbook.

## Procédure

1. appliquer le patch ou remplacer le dépôt ;
2. commit et push ;
3. déployer avec vérification navigateur ;
4. vérifier la version `4.4.0` ;
5. confirmer que le produit modèle seul fonctionne ;
6. activer un plafond de trois crédits et le shadow ;
7. lancer une capture manuelle ;
8. régler les résultats après les matchs ;
9. optimiser sans fournisseur ;
10. refermer le pare-feu.
