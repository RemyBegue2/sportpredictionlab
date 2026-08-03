# Audit multi-rôles — V3.8 Cloud Evidence Run & Data Quality Gate

## Verdict consolidé

**GO technique** pour déployer la V3.8 et lancer un premier lot historique plafonné.

**NO-GO statistique** pour toute affirmation de rentabilité, promotion automatique ou recommandation de mise. Un lot de 30 événements valide d'abord la chaîne de données ; il ne démontre pas un avantage contre le marché.

## 1. Utilisateur sans Python local

### Retour
Le parcours ne doit contenir aucune commande locale.

### Décision appliquée
Deux workflows manuels remplacent les scripts locaux :

1. `Estimate historical sample` produit un identifiant `REQ-...` sans appeler le fournisseur.
2. `Run historical sample` exige cet identifiant, les mêmes paramètres et la confirmation `EXECUTE_APPROVED_SAMPLE`.

Le rapport est publié dans GitHub puis affiché sur Railway.

## 2. Product Owner

### Retour
Le dashboard devait distinguer la santé technique de la qualité des preuves.

### Décision appliquée
Une section **Preuves et benchmark** affiche :

- porte qualité ;
- couverture des événements ;
- couverture Winamax ;
- crédits consommés ;
- blocages et avertissements ;
- taille de l'échantillon accepté.

## 3. Data Engineer

### Retour
Une collecte réussie peut rester inutilisable si les événements sont incomplets, dupliqués ou mal rapprochés.

### Décision appliquée
Le rapport calcule :

- couverture événementielle ;
- couverture Winamax ;
- doublons sur événement/bookmaker/marché/sélection/snapshot ;
- taux de matching fiable ;
- lignes acceptées et mises en quarantaine.

Les rapprochements ambigus ne sont pas transformés silencieusement en matchs valides.

## 4. Auditeur anti-fuite

### Retour
La cote utilisée doit être strictement antérieure au coup d'envoi.

### Décision appliquée
La porte temporelle impose :

```text
requested_snapshot_at < commence_time
```

Une égalité ou une cote postérieure au match bloque la porte qualité et place la ligne dans la quarantaine.

Le benchmark existant conserve ses contrôles plus complets sur `prediction_created_at` et `result_available_at`.

## 5. Statisticien

### Retour
Un petit lot ne doit pas produire un verdict de performance excessif.

### Décision appliquée
Les statuts sont déterministes :

- `blocked` : qualité insuffisante ;
- `technical_validation` : moins de 100 lignes ;
- `exploratory` : de 100 à 999 lignes ;
- `analysis_ready` : au moins 1 000 lignes propres.

Même `analysis_ready` ne constitue pas une preuve de rentabilité.

## 6. Quant / analyste de marché

### Retour
Le benchmark doit comparer les mêmes événements au modèle, à Winamax et au consensus.

### Décision appliquée
Après la collecte, le workflow tente automatiquement de préparer un benchmark T−1 h avec :

- modèle walk-forward ;
- Winamax dévigé ;
- consensus dévigé ;
- blend fixe 50/50 déjà présent dans le moteur.

Le rapport de preuve intègre le benchmark lorsqu'il existe. Son absence n'est pas masquée.

## 7. ML Engineer

### Retour
Une nouvelle release ne doit pas réécrire les anciennes prédictions ni promouvoir un modèle automatiquement.

### Décision appliquée
La V3.8 ne modifie ni le champion ni le registre des modèles. Elle produit uniquement de la preuve et un diagnostic de qualité. La promotion automatique reste désactivée.

## 8. FinOps

### Retour
Le coût doit être borné avant le premier appel.

### Décision appliquée
Plafonds codés :

```text
30 événements maximum
31 appels de découverte maximum
200 crédits historiques maximum
```

Le `REQ-...` dépend de tous les paramètres et change si un plafond, une date, un horizon ou un bookmaker change.

## 9. SRE / DevOps

### Retour
Ajouter un troisième service Railway aurait créé une nouvelle cible fragile après les incidents de service ID.

### Décision appliquée après contre-audit
Le lot historique s'exécute dans un job GitHub Actions isolé, pas dans le service web et pas dans le cron. Les checkpoints et résultats utiles sont persistés dans PostgreSQL. Le dashboard est ensuite redéployé sur Railway avec une vérification `/api/release`.

Cette décision réduit la surface opérationnelle sans réintroduire de dépendance locale.

## 10. QA

### Retour
Le contrôle doit couvrir le code, les workflows et le rendu.

### Décision appliquée
Validation effectuée :

- 117 tests ;
- contrats API ;
- contrats HTML/JavaScript ;
- syntaxe JavaScript ;
- parsing de tous les workflows YAML ;
- test de l'identifiant de plan immuable ;
- test des plafonds ;
- test de quarantaine temporelle ;
- test du endpoint `/api/evidence` ;
- test navigateur étendu à la section Preuves.

## 11. Sécurité

### Retour
Les clés et URLs sensibles ne doivent pas entrer dans les rapports ni les artefacts de reprise.

### Décision appliquée
Les workflows lisent les secrets GitHub sans les recopier dans les JSON. Le rapport ne contient ni clé API, ni token Railway, ni mot de passe, ni `DATABASE_URL`.

## 12. Responsable jeu responsable

### Retour
Une interface de preuve ne doit pas devenir un écran d'incitation.

### Décision appliquée
Le contrat public et le rapport conservent :

```text
profitability_claim = false
stake_recommendation = false
automatic_bet_placement = false
```

## Risques résiduels

1. La disponibilité historique de Winamax peut être inférieure à celle du consensus.
2. Les crédits de découverte sont plafonnés en nombre d'appels, mais le fournisseur reste la source de vérité sur leur coût réel.
3. Un échec de qualité publie le diagnostic puis fait échouer le workflow volontairement.
4. Le premier lot peut ne produire aucun benchmark si les résultats ou le matching sont insuffisants.
5. Le workflow pousse un rapport dans la branche ; une protection de branche trop stricte peut exiger une adaptation par Pull Request.

## Décision finale

La V3.8 est exploitable pour la première collecte contrôlée. La prochaine version devra être choisie à partir du rapport réel, pas avant.
