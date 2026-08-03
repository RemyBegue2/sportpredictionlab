# Audit multi-rôles — Sports Prediction Lab V4.3.0

## Verdict consolidé

- **Code V4.3.0 : GO pour déploiement contrôlé.**
- **Calendrier et probabilités modèle seul : GO, zéro crédit fournisseur.**
- **Cotes quotidiennes payantes : désactivées par défaut.**
- **Campagnes historiques payantes : suspendues par défaut.**
- **Shortlist de marché : NO-GO tant qu’une validation live séparée n’est pas obtenue.**
- **Pari automatique, recommandation de mise et promotion automatique : interdits.**

## Constat de départ

La V4.2 a correctement évité un nouveau backfill historique non viable, mais elle ne répondait pas au besoin produit immédiat : voir les rencontres couvertes, vérifier que le modèle fonctionne et obtenir ses probabilités sans payer des données de marché. La V4.3 sépare donc le produit quotidien de l’évaluation historique.

## Arbitrage par rôle

### Product Owner

Le premier écran utile doit fonctionner sans bookmaker. Le produit affiche désormais les rencontres du jour, les rencontres à venir dans un horizon de 31 jours, les probabilités 1N2, la couverture du modèle et les motifs précis d’absence de shortlist.

L’audit a corrigé un défaut de conception important : un horizon initial de 7 jours aurait encore affiché un produit vide pendant l’intersaison. L’horizon par défaut est maintenant de 31 jours.

### Data Engineer

Le calendrier ne dépend plus de The Odds API. Une source composite utilise :

1. le scoreboard ESPN non authentifié comme source primaire ;
2. le CSV de fixtures Football-Data comme repli ;
3. un cache local de six heures ;
4. un backoff après panne totale des sources.

Les téléchargements sont limités à 5 Mo et lus en streaming. Les identifiants de rencontre sont stables entre alias de fournisseurs et petits changements d’heure. Les noms de clubs actuels sont normalisés vers ceux du modèle.

### Ingénieur ML

Le modèle embarqué passe les contrôles d’intégrité et produit des probabilités valides. Il reste cependant enregistré en `shadow`. Les clubs absents de l’historique récent ne sont plus supprimés : ils reçoivent une prédiction cold-start, rétractée vers les priors de championnat et explicitement marquée comme faible couverture.

Une prédiction cold-start ne peut jamais être considérée comme éligible au marché. Le système distingue donc :

- `historical_team_coverage` ;
- `cold_start_league_priors`.

### Quant / Statisticien

Une probabilité modèle n’est pas une recommandation de pari. La V4.3 maintient `market_shortlist=false` tant que les conditions suivantes ne sont pas réunies : cotes fraîches, validation live, calibration suffisante et protocole d’avantage au marché défini à l’avance.

Une journée sans match ou une shortlist vide est un résultat valide et expliqué. Aucun signal n’est créé pour remplir artificiellement l’interface.

### FinOps

Le mode quotidien normal consomme zéro crédit. Les valeurs par défaut sont :

```text
DAILY_ODDS_ENABLED=false
DAILY_ODDS_MAX_CREDITS=0
HISTORICAL_EVIDENCE_ENABLED=false
SHADOW_MODE_ENABLED=false
```

L’interface ne sonde plus les endpoints de cotes payantes lorsque le pare-feu est fermé. Les workflows historiques payants exigent à la fois une variable GitHub explicite et leur confirmation humaine existante.

### SRE

Le cron exécute le produit modèle seul toutes les six heures. Le workflow `Refresh daily product` vérifie qu’aucun crédit n’a été consommé. Les rafraîchissements sont idempotents ; PostgreSQL utilise un verrou transactionnel consultatif pour éviter les doublons lorsque le cron et l’API travaillent simultanément.

L’API ne bloque pas chaque affichage sur les sources externes : elle réutilise les prédictions persistées et un rafraîchissement vide récent. Les déploiements Railway conservent le mécanisme stabilisé `railway up --detach` suivi d’une vérification publique stricte.

### QA

La validation finale contient **205 tests**, tous réussis dans cinq lots disjoints. Les nouvelles régressions couvrent notamment :

- horizon quotidien de 31 jours ;
- alias des clubs actuels ;
- stabilité de l’identifiant de rencontre ;
- repli ESPN/Football-Data et backoff réseau ;
- limitation de taille des réponses ;
- prédiction cold-start pour un promu ;
- absence d’appel aux cotes lorsque le pare-feu est fermé ;
- idempotence des prédictions ;
- état hors saison avec rencontres à venir ;
- smoke test navigateur du panneau quotidien.

### Sécurité

Les hôtes externes sont figés, aucune URL arbitraire n’est acceptée et aucune clé n’est nécessaire pour le calendrier. Les erreurs réseau sont réduites au type d’erreur sans exposer de secret. ESPN reste une dépendance non officielle et remplaçable ; elle n’est jamais le seul chemin de calendrier.

### Responsable usage

Le produit ne place aucun pari, ne recommande aucune mise, ne se connecte à aucun compte bookmaker et ne revendique aucune rentabilité. Les cold-start et l’absence de validation marché sont visibles dans l’interface.

## Corrections issues de l’audit croisé

1. horizon par défaut porté de 7 à 31 jours ;
2. normalisation de Leeds, Ipswich, Sunderland, Coventry, Hull et autres alias ;
3. prédictions cold-start rétractées vers les priors de championnat ;
4. cold-start interdit pour toute shortlist marché ;
5. identifiants de rencontre stabilisés entre fournisseurs ;
6. backoff de 15 minutes après panne totale du calendrier ;
7. téléchargement streaming limité à 5 Mo ;
8. cache et prédictions persistées utilisés avant tout nouvel appel externe ;
9. aucun sondage d’endpoint payant depuis l’interface lorsque le pare-feu est fermé ;
10. verrou PostgreSQL contre les doublons concurrents ;
11. smoke test renforcé sur le produit quotidien et les erreurs frontend ;
12. états shadow/backfill suspendus présentés comme volontaires, pas comme pannes.

## Risques résiduels

- La connectivité réelle aux deux sources gratuites n’a pas été validée dans l’environnement de préparation.
- ESPN est une API non officielle susceptible de changer.
- Le CSV Football-Data est un repli et sa fraîcheur dépend de sa publication.
- Les prédictions cold-start sont exploratoires et non éligibles au marché.
- Aucune shortlist de marché validée n’existe encore.
- Les actions GitHub restent principalement référencées par tags majeurs plutôt que par SHA immuables.
- Alembic reste à introduire avant des migrations complexes.

## Décision finale

La V4.3.0 est prête à être déployée pour vérifier le produit quotidien à coût nul. Les dépenses fournisseur restent gelées. La prochaine décision ne doit être prise qu’après plusieurs rafraîchissements réels réussis du calendrier et des probabilités modèle seules.
