# Audit multi-rôles — Sports Prediction Lab V3.3 Shadow Mode

## Verdict exécutif

La V3.3 est un **GO technique pour une application privée de recherche sur Railway**, avec un service web et un service cron séparé. Elle est conçue pour observer automatiquement les rencontres, figer les probabilités avant le coup d’envoi, conserver la cote horodatée, récupérer les résultats et produire des métriques.

Elle reste un **NO-GO statistique pour toute revendication de rentabilité**, un **NO-GO pour le placement automatique de paris** et un **NO-GO pour une ouverture publique multi-utilisateur**.

Le constat le plus important de l’audit est défavorable au modèle actuel mais sain pour le produit : le modèle football embarqué est entraîné sur seulement 90 rencontres EPL, arrêtées au 23 octobre 2023. Pour des rencontres en 2026, il est automatiquement classé `degraded` et toute sélection opérationnelle est bloquée. Les probabilités restent visibles afin de tester et mesurer le système, pas afin de les présenter comme actuelles.

## Périmètre audité

- FastAPI et interface web privée ;
- PostgreSQL ;
- The Odds API et bookmaker `winamax_fr` ;
- modèle football 1N2 ;
- modèle tennis Elo expérimental ;
- journal shadow append-only ;
- rapprochement des résultats ;
- tâches Railway ;
- sécurité, quota, observabilité et usage responsable.

Aucun appel réel à The Odds API n’a été effectué pendant la fabrication de cette version. Aucun crédit n’a été consommé et aucune clé n’est incluse dans l’archive.

---

## 1. Product owner

### Retour

La V3.2 demandait encore beaucoup d’actions manuelles. Le produit doit désormais produire une preuve continue plutôt qu’une succession de démonstrations ponctuelles.

### Décisions intégrées

- ajout d’une section **Shadow mode** ;
- journal des prédictions figées ;
- dernier cycle automatique visible ;
- nombre de prédictions et de résultats évalués ;
- maturité de l’échantillon ;
- log-loss et résultat fictif normalisé ;
- statut explicite du modèle et date de ses données ;
- possibilité permanente d’afficher zéro candidat.

### Réserve

Le produit n’est pas encore « autonome » tant que le second service Railway utilisant `railway.cron.toml` n’est pas créé.

---

## 2. Auditeur anti-fuite temporelle

### Retour

Une prédiction historique n’a de valeur que si elle était réellement disponible avant le match. Une ligne recalculée après coup doit être exclue, même si ses chiffres semblent plausibles.

### Décisions intégrées

Chaque prédiction shadow conserve :

- `prediction_created_at` ;
- `odds_observed_at` ;
- `commence_time` ;
- `data_cutoff` ;
- `model_id` et `model_version` ;
- une empreinte SHA-256 du contenu ;
- le verdict du contrôle temporel.

Règles :

```text
odds_observed_at <= prediction_created_at < commence_time
```

Les violations sont enregistrées avec le statut `invalid`. Elles ne sont jamais réparées silencieusement ni incluses dans les métriques.

### Correction importante

Les prédictions shadow utilisent une table séparée des prédictions interactives. Les anciennes observations ne sont donc pas modifiées lorsqu’un utilisateur recalcule le même match.

---

## 3. Statisticien

### Retour

Enregistrer une nouvelle prédiction toutes les quinze minutes gonflerait artificiellement l’échantillon avec des observations fortement corrélées du même match.

### Décisions intégrées

Une seule observation est autorisée par :

```text
événement + modèle + version + horizon
```

Horizons :

- `t-24h` ;
- `t-6h` ;
- `t-1h` ;
- `pre-close`.

La dernière catégorie n’est volontairement pas appelée « closing line ». Avec un cron toutes les quinze minutes, une vraie cote de clôture ne peut pas être garantie. `pre-close` couvre la dernière fenêtre de vingt minutes. La véritable closing line reste une donnée d’évaluation obtenue séparément.

Les métriques sont calculées séparément par horizon. La vue principale utilise `t-1h` lorsqu’elle dispose de résultats.

Maturité :

- moins de 100 résultats : anecdotique ;
- 100 à 299 : exploratoire ;
- 300 à 499 : signal préliminaire ;
- 500 et plus : première évaluation sérieuse.

### Réserve

Ces seuils ne prouvent pas à eux seuls un avantage. La diversité temporelle, les intervalles de confiance et la comparaison au marché restent obligatoires.

---

## 4. Quant marchés

### Retour

Une bonne accuracy ne suffit pas. Le système doit être comparé à Winamax et au consensus dévigué, et la qualité du prix doit être évaluée séparément du résultat du match.

### Décisions intégrées

Pour chaque observation football :

- probabilités du modèle ;
- cotes Winamax ;
- marge du marché ;
- probabilités déviguées ;
- edge ;
- EV brute ;
- EV après marge d’incertitude ;
- décision et motifs ;
- résultat final ;
- log-loss, Brier, RPS et accuracy ;
- résultat fictif à une unité uniquement pour l’évaluation.

### Veto

Le modèle actuel étant trop ancien, une éventuelle shortlist calculée par le comparateur est vidée et remplacée par une abstention opérationnelle. L’observation est néanmoins conservée afin de mesurer le niveau réel de ce modèle dégradé.

---

## 5. Trader de cotes

### Retour

Une cote sans heure, incomplète ou ancienne ne doit jamais apparaître comme un signal valide.

### Décisions intégrées

- marché 1N2 complet obligatoire ;
- bookmaker et heure de mise à jour conservés ;
- blocage après le coup d’envoi ;
- statut `à actualiser` lorsque l’heure manque ou que le prix est ancien ;
- aucune sélection lorsque Winamax est absent ;
- consensus calculé hors Winamax ;
- conservation du prix observé au moment exact du snapshot shadow.

### Réserve

The Odds API et Winamax peuvent afficher des prix différents à quelques secondes d’intervalle. L’interface continue de demander une vérification directe avant toute décision personnelle.

---

## 6. Ingénieur ML

### Retour

Le modèle football n’est pas seulement petit : il est périmé pour les fixtures 2026. L’application doit le dire et le traiter comme un défaut opérationnel.

### Décisions intégrées

- paramètre `MODEL_MAX_AGE_DAYS`, 365 jours par défaut ;
- calcul de l’âge du modèle par rapport à la date du match ;
- statut `degraded_stale` dans les prédictions ;
- statut `degraded` dans le registre des modèles ;
- veto automatique sur les candidats ;
- registre conservant chaque couple `model_id + version` au lieu d’écraser l’historique ;
- empreinte du jeu d’artefacts et date d’entraînement enregistrées.

### Prochaine obligation

Réentraîner le football sur plusieurs saisons récentes, puis effectuer une calibration et une validation chronologiques. Tant que cela n’est pas fait, le shadow mode évalue surtout une baseline ancienne et l’infrastructure.

---

## 7. Spécialiste football

### Retour

Le périmètre doit rester étroit : Premier League et 1N2 avant d’ajouter corners, buteurs ou combinés.

### Décisions intégrées

- `soccer_epl` uniquement par défaut ;
- modèle 1N2 pré-match ;
- retrait des événements in-play ;
- correspondance d’identité vers les noms du modèle ;
- abstention si une équipe n’est pas couverte ;
- collecte des scores après un délai de 105 minutes, afin d’éviter de demander inutilement des résultats pendant le match.

### Réserve

Le modèle embarqué ne connaît pas les transferts, blessures, entraîneurs et compositions de 2026.

---

## 8. Spécialiste tennis

### Retour

Le tennis ne doit pas hériter du statut football. Le snapshot ATP n’a que deux timestamps de tournoi et ne permet pas une calibration honnête.

### Décisions intégrées

- modèle tennis maintenu en `experimental` ;
- Elo non calibré ;
- veto sur toute sélection ;
- collecte de marché techniquement possible ;
- résultat non promu dans la synthèse football.

### NO-GO

Aucune stratégie tennis avant une reconstruction multi-saisons avec dates exactes, surfaces, tours, abandons et calibration chronologique.

---

## 9. Data engineer

### Retour

Les données doivent rester reproductibles et dédupliquées malgré les redémarrages et les appels répétés.

### Décisions intégrées

Nouvelles tables :

- `shadow_predictions` ;
- `model_registry` ;
- `shadow_cycles`.

Contraintes :

- empreinte unique ;
- unicité événement/modèle/version/horizon ;
- résultats liés à l’identifiant fournisseur ;
- snapshots de cotes immuables ;
- cycle et erreurs durables ;
- migration compatible depuis une base V3.2.1.

### Réserve

La synthèse charge au maximum 10 000 observations et signale explicitement si elle est tronquée. Une future version devra agréger nativement en SQL lorsque le volume devient important.

---

## 10. FinOps / quota The Odds API

### Retour

Un cycle automatique ne doit pas vider silencieusement le quota.

### Décisions intégrées

- `SHADOW_QUOTA_FLOOR`, 100 crédits par défaut ;
- arrêt propre avec statut `quota_guard` sous le plancher ;
- une seule requête h2h groupant les bookmakers ;
- résultats demandés uniquement pour les événements arrivés à échéance ;
- pas de recherche générale des scores lorsque rien n’est dû ;
- historique coûteux maintenu dans un worker distinct et manuel.

### Réserve

Le coût réel dépend du plan fournisseur et de la fréquence. Le premier cycle Railway doit être surveillé dans les en-têtes de quota.

---

## 11. SRE / DevOps

### Retour

Le service web ne doit pas héberger une boucle infinie ni exécuter les collectes longues.

### Décisions intégrées

Trois configurations séparées :

```text
railway.toml          service web
railway.cron.toml     cycle shadow toutes les 15 minutes
railway.worker.toml   backfill historique manuel
```

Le cycle shadow est fini et quitte proprement. Sa politique de redémarrage est `NEVER`, ce qui évite une répétition coûteuse après une erreur.

Le service web conserve :

- healthcheck ;
- readiness ;
- migration pré-déploiement ;
- démarrage Docker reproductible.

### GO conditionnel

Le cron doit être créé comme second service Railway et observé pendant au moins un cycle complet.

---

## 12. Sécurité

### Retour

Le shadow mode crée des actions automatiques et des journaux supplémentaires. Les secrets et endpoints doivent rester privés.

### Décisions intégrées

- clé The Odds API exclusivement en variable serveur ;
- aucune clé dans le cache, le frontend ou les rapports ;
- authentification et cookie sécurisé en production ;
- protection CSRF des écritures ;
- CSP stricte ;
- erreurs persistées sous forme de type, sans URL contenant la clé ;
- aucune requête fournisseur arbitraire exposée au navigateur ;
- PostgreSQL requis en production.

### Risques restants

- sauvegarde et restauration PostgreSQL à tester sur le compte Railway ;
- rotation des secrets à documenter opérationnellement ;
- absence de gestion multi-utilisateur ;
- pas de WAF ou de contrôle d’accès par rôle.

---

## 13. QA

### Contrôles intégrés

La suite finale comporte **71 tests réussis** et **85 % de couverture globale**. Le moteur shadow atteint 86 %, la persistance 89 % et le cycle cron 81 %.

- ordre temporel valide et invalide ;
- quarantaine ;
- unicité par horizon ;
- rejet des prédictions à plus de 24 heures ;
- fenêtre `pre-close` ;
- règlement après résultat ;
- log-loss, Brier et RPS ;
- registre multi-version ;
- modèle périmé et veto ;
- quota guard ;
- orchestration d’un cycle ;
- migration V3.2.1 vers V3.3 ;
- endpoints shadow ;
- syntaxe JavaScript ;
- configurations Railway/Render.

### Limites QA

- aucun cycle réel avec la clé de l’utilisateur ;
- aucun conteneur construit sur Railway dans cet environnement ;
- aucun test de restauration PostgreSQL ;
- validation visuelle dynamique limitée par la politique réseau du navigateur de test local.

---

## 14. Responsable jeu responsable et conformité

### Décisions intégrées

- aucune connexion au compte Winamax ;
- aucun placement automatique ;
- aucune taille de mise ;
- aucune martingale ;
- aucun objectif quotidien ;
- une unité fictive uniquement comme métrique expérimentale ;
- affichage des abstentions ;
- modèle périmé bloqué ;
- aucune promesse de gain.

Le shadow mode sert à vérifier une hypothèse, pas à augmenter la fréquence de jeu.

---

## Risques classés

### Critiques avant toute conclusion sportive

1. Données football arrêtées au 23 octobre 2023.
2. Aucun historique shadow réel encore collecté.
3. Aucun benchmark récent contre Winamax et consensus.
4. Tennis non calibré.

### Élevés avant une ouverture publique

1. Authentification mono-utilisateur.
2. Sauvegardes et restauration non testées.
3. Pas de limitation par utilisateur.
4. Pas de surveillance externe ni alertes.
5. Droits des données tennis incompatibles avec un usage commercial sans accord.

### Moyens

1. Couverture de l’orchestrateur historique plus faible que le cœur métier.
2. Closing line réelle obtenue séparément du jalon `pre-close`.
3. Matching d’entités encore limité au périmètre EPL connu.

---

## Critères de succès V3.3

- service cron actif ;
- au moins 14 jours sans rupture critique ;
- aucun enregistrement temporel invalide dans les métriques ;
- prédictions uniques par horizon ;
- résultats récupérés et réglés automatiquement ;
- quota respecté ;
- modèles et dates visibles ;
- sauvegarde PostgreSQL restaurée une fois ;
- zéro placement automatique.

## Verdict final

**GO :** déploiement privé, shadow mode, collecte contrôlée et mesure technique.

**GO conditionnel :** observation sportive après réentraînement du modèle football et plusieurs centaines de résultats hors temps.

**NO-GO :** rentabilité annoncée, mise recommandée, automatisation Winamax, tennis promu ou service public.
