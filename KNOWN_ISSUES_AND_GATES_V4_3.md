# Risques et portes — V4.3.0

## Portes avant toute dépense fournisseur

Les cotes quotidiennes et campagnes historiques doivent rester désactivées jusqu’à ce que :

1. trois rafraîchissements quotidiens consécutifs récupèrent ou réutilisent correctement le calendrier ;
2. les probabilités du modèle soient produites sans erreur ni doublon ;
3. `/api/model-diagnostics` reste `operational_research` ou mieux ;
4. `/api/credit-firewall` confirme zéro crédit autorisé ;
5. les cold-start soient clairement visibles et exclus du marché ;
6. l’utilisateur approuve une expérience de marché limitée avec un plafond séparé.

## Risques P1

- source ESPN non officielle ;
- fraîcheur du repli Football-Data non garantie contractuellement ;
- aucune troisième source officielle sans clé ;
- modèle encore en statut `shadow` ;
- clubs promus évalués en cold-start tant que leur historique n’est pas enrichi ;
- actions GitHub non toutes figées par SHA ;
- absence d’Alembic ;
- rate limiter local au processus.

## Hors périmètre

- promesse de pari du jour ;
- recommandation de mise ;
- placement automatique ;
- connexion à un compte bookmaker ;
- promotion automatique ;
- conclusion de rentabilité ;
- réactivation automatique des campagnes evidence.
