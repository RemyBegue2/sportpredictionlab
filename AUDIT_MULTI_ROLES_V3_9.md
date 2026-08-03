# Audit multi-rôles V3.9 — Data Reliability & Coverage Funnel

## Point de départ observé

Le premier lot historique publié en production affichait :

- 111 événements découverts ;
- 10 événements avec cotes ;
- 63 lignes acceptées ;
- 9,0 % de couverture événements ;
- 2,7 % de couverture Winamax ;
- 100 crédits consommés ;
- porte qualité bloquée.

Le code V3.8 calculait `events_with_odds / événements_découverts`. Ce dénominateur mélangeait le vivier découvert avec les événements que le plafond de crédits permettait réellement de sélectionner et d’interroger. Un événement écarté avant appel fournisseur était donc compté comme un échec fournisseur.

La V3.9 remplace ce ratio par un funnel avec des dénominateurs explicites.

## 1. Product Owner

### Retour

Le mot « bloquée » ne disait pas où les événements disparaissaient ni quelle action effectuer.

### Décision intégrée

La page affiche désormais :

```text
Découverts
→ demandés
→ sélectionnés avec le budget
→ requêtes terminées
→ cibles retournées
→ événements rapprochés
→ consensus disponible
→ Winamax disponible
```

Chaque porte affiche sa propre raison et la prochaine action utile.

## 2. Utilisateur sans Python local

### Retour

Aucune correction ne doit nécessiter de terminal ou de script exécuté sur l’ordinateur.

### Décision intégrée

Le workflow **Recompute latest evidence** :

1. récupère le dernier artefact historique GitHub ;
2. recalcule les ratios ;
3. exécute les tests ;
4. publie les nouveaux fichiers ;
5. redéploie Railway ;
6. vérifie `/api/release`.

Il ne demande ni Python local, ni clé The Odds API, ni `DATABASE_URL`.

## 3. Data Engineer

### Retour

Le plan connaissait déjà le nombre d’événements sélectionnés, mais le rapport l’ignorait. Les événements non sélectionnés n’avaient pas de statut final.

### Décision intégrée

Les nouveaux plans écrivent `event_selection.csv` avec exactement un statut par événement :

```text
selected
not_selected_budget_limit
not_selected_sample_limit
```

Après exécution, le rapport complète ces statuts avec :

```text
accepted
provider_event_missing
temporal_violation
matching_ambiguous
result_missing_or_unmatched
```

Les anciens artefacts V3.8 restent recalculables. Lorsqu’un ancien plan ne contient pas `event_selection.csv`, le rapport utilise le statut explicite `not_selected_sample_or_budget_limit` au lieu d’inventer une séparation impossible à prouver.

## 4. Intégrateur fournisseur

### Retour

La couverture fournisseur doit utiliser uniquement les cibles effectivement exécutées.

### Décision intégrée

Formule V3.9 :

```text
provider_returned_event_snapshots
---------------------------------
completed_event_snapshots
```

Les 111 événements découverts restent visibles dans le funnel, mais ne sont plus le dénominateur de la couverture fournisseur.

## 5. Auditeur anti-fuite

### Retour

La correction des dénominateurs ne doit pas diminuer les contrôles temporels.

### Décision intégrée

Toute ligne doit conserver :

```text
requested_snapshot_at < commence_time
```

Une violation bloque l’intégrité technique et place l’événement en `temporal_violation`. Aucune ligne n’est réparée silencieusement.

## 6. Statisticien

### Retour

Une chaîne technique correcte sur dix événements ne permet aucune conclusion sur le modèle.

### Décision intégrée

La preuve statistique est indépendante des autres portes :

```text
< 30       validation technique
30–99      validation du pipeline
100–299    exploratoire
300–999    préliminaire
≥ 1000     première analyse sérieuse
```

Une bonne couverture fournisseur ne transforme jamais un petit lot en preuve de rentabilité.

## 7. Quant / analyste de marché

### Retour

Winamax et le consensus ne doivent pas partager la même porte.

### Décision intégrée

- **Consensus disponible** : au moins deux marchés bookmaker complets sur une cible.
- **Winamax disponible** : marché Winamax complet sur une cible.

Une faible couverture Winamax n’empêche plus une analyse du consensus, mais bloque une comparaison dédiée à Winamax.

## 8. ML Engineer

### Retour

Le rapport de données ne doit pas modifier le champion ni promouvoir un challenger.

### Décision intégrée

La V3.9 ne change aucun modèle et ne modifie aucune transition du registre. Le rapport reste une preuve de données, pas un moteur de promotion.

## 9. FinOps

### Retour

Cent crédits ont déjà été consommés. Le diagnostic suivant doit être gratuit.

### Décision intégrée

**Recompute latest evidence** n’appelle jamais The Odds API. Le workflow ne référence même pas `THE_ODDS_API_KEY`.

Le rapport publie toujours les crédits du lot d’origine, mais les crédits consommés par le recalcul sont zéro.

## 10. SRE / DevOps

### Retour

Le recalcul doit utiliser les données exactes du run réel et confirmer le déploiement.

### Décision intégrée

Le workflow télécharge le plus récent artefact non expiré dont le nom commence par :

```text
historical-sample-evidence-
```

Il échoue avant tout déploiement si l’artefact ou ses fichiers indispensables sont absents. Après publication, il déploie le service web et compare version, commit et hash du modèle avec `/api/release`.

### Risque restant

Les artefacts GitHub sont conservés pendant une durée limitée. Si le dernier artefact a expiré et qu’aucune copie n’a été téléchargée, le lot brut n’est plus recalculable sans nouvelle collecte. Le workflow signale ce cas explicitement ; il ne consomme pas automatiquement de nouveaux crédits.

## 11. QA

### Retour

Le cas réel 111 découverts / 10 cibles retournées devait être reproduit dans les tests.

### Décision intégrée

Un test de régression construit exactement ce type de funnel et vérifie notamment :

```text
couverture fournisseur = 10 / 10 = 100 %
Winamax = 3 / 10 = 30 %
consensus = 10 / 10 = 100 %
planned_events = 10, pas 111
```

Ces valeurs sont celles du scénario de test. Le workflow recalculera les valeurs exactes du vrai artefact ; il ne suppose pas que le vrai résultat sera identique.

## 12. Red Team

### Retour

Le nouveau dashboard ne doit pas continuer d’afficher les anciens ratios V3.8 avant recalcul.

### Décision intégrée

Lorsque seul `evidence_report_v3_8.json` existe, `/api/evidence` renvoie :

```text
Recalcul requis
```

Les anciens 9,0 % et 2,7 % ne sont plus présentés comme des métriques fiables. L’interface indique le workflow zéro crédit à lancer.

## 13. Sécurité

### Retour

Le recalcul lit des artefacts GitHub mais ne doit exporter aucun secret.

### Décision intégrée

Le rapport contient uniquement des événements, statuts, taux, hashes et métriques. Aucun environnement, token, mot de passe, clé fournisseur ou URL de base de données n’est exporté.

## 14. Responsable jeu responsable

### Retour

La correction d’un ratio peut donner une impression injustifiée d’amélioration du modèle.

### Décision intégrée

Le dashboard conserve :

- aucune recommandation de mise ;
- aucune affirmation de rentabilité ;
- aucun pari automatique ;
- aucune promotion automatique ;
- une porte statistique indépendante et généralement insuffisante sur un petit lot.

## Verdict consolidé

### GO

- déployer V3.9 ;
- recalculer le dernier artefact sans crédit ;
- lire séparément fournisseur, matching, consensus, Winamax et preuve statistique.

### NO-GO

- lancer immédiatement un nouveau lot payant ;
- modifier le modèle à partir de ce petit échantillon ;
- annoncer une performance ou proposer une mise.

La prochaine version doit être décidée après le recalcul réel V3.9, pas avant.
