# Audit multi-rôles — V4.0 Controlled Evidence Scale-Up

## Question auditée

Comment passer du petit lot V3.9.2 à des campagnes de 30, 100, 300 puis 1 000 observations sans Python local, sans identifiant à recopier, sans fuite temporelle, sans dépassement silencieux du budget et sans promotion automatique du modèle ?

## Retours des rôles et décisions intégrées

### Utilisateur non-développeur

**Retour :** les procédures précédentes demandaient trop de fichiers, d’identifiants et de paramètres techniques.

**Décision :** un seul workflow `Run evidence campaign` avec quatre champs utiles : mode, stage cible, plafond de crédits et baseline. Aucun `REQ`, `plan_id` ou hash n’est saisi manuellement.

### Product Owner

**Retour :** le dashboard doit répondre à « où en est la preuve ? » avant d’afficher les détails.

**Décision :** ajout d’un rapport de campagne et d’une synthèse web : stage terminé, prochain stage, porte qualité, budget autorisé et crédits observés.

### Data Engineer

**Retour :** les campagnes doivent conserver un état immuable et récupérable.

**Décision :** chaque exécution publie le plan, les événements découverts et sélectionnés, le plan fournisseur, les checkpoints, les cotes normalisées et les rapports dans un artefact GitHub dédié.

### Intégrateur fournisseur

**Retour :** le budget de découverte et le budget des snapshots doivent rester dans un plafond global.

**Décision :** le plan calcule un nombre d’appels de découverte adapté au stage, retranche leur coût observé puis transmet uniquement le budget restant au plan de snapshots.

### Statisticien

**Retour :** passer au stage suivant ne peut pas dépendre du ROI.

**Décision :** la porte de scale-up exige l’intégrité temporelle, zéro doublon, une couverture fournisseur d’au moins 80 %, un matching fiable d’au moins 95 % et une couverture consensus d’au moins 70 %. Le stage 1 reste une validation technique.

### Quant marché

**Retour :** Winamax peut être rare alors que le consensus reste exploitable.

**Décision :** la baseline principale est choisie dans le formulaire (`consensus` ou `winamax`), mais les deux couvertures restent mesurées séparément. Le consensus est la valeur par défaut.

### Auditeur anti-fuite

**Retour :** l’augmentation du volume ne doit jamais détendre les contrôles temporels.

**Décision :** le workflow réutilise le rapport V3.9, qui met en quarantaine les observations temporellement invalides. Une violation bloque le passage au stage suivant.

### ML Engineer

**Retour :** une campagne de preuve ne doit pas devenir un mécanisme de promotion.

**Décision :** aucun appel de transition du registre des modèles n’est présent dans le workflow. Les rapports déclarent explicitement `automatic_model_promotion: false`.

### FinOps

**Retour :** une campagne ne doit pas démarrer si le budget ne peut pas financer le stage complet.

**Décision :** `start_next_stage` est bloqué lorsque la capacité estimée est inférieure au stage demandé. `dry_run` ne consomme aucun crédit. Le plafond autorisé est compris entre 0 et 20 000 crédits.

### SRE / DevOps

**Retour :** les anciens mélanges de versions et les reprises imprécises ont provoqué plusieurs échecs.

**Décisions :**

- tests complets avant le premier appel fournisseur ;
- contrôle des marqueurs V4 avant exécution ;
- aucun usage de `DATABASE_URL` dans la campagne ;
- déploiement vérifié par version, commit et hash du modèle ;
- checkpoint GitHub restauré uniquement si stage, baseline, budget et dates correspondent exactement ;
- en l’absence de checkpoint compatible, démarrage frais annoncé clairement.

### QA

**Retour :** les régressions précédentes doivent devenir des tests permanents.

**Décision :** tests sur le budget insuffisant, le stage 100, l’absence de PostgreSQL, la sélection déterministe, le contrat frontend/API, la reprise compatible et la conservation des dates entre deux continuations.

### Sécurité

**Retour :** les artefacts ne doivent pas contenir les secrets cloud.

**Décision :** la campagne ne sérialise jamais les variables d’environnement. Les secrets restent injectés uniquement par GitHub Actions.

### Responsable jeu responsable

**Retour :** une campagne plus grande ne constitue pas une recommandation de pari.

**Décision :** aucun montant, aucune exécution de pari, aucune promesse de rentabilité et aucune promotion automatique. Le rapport reste expérimental.

## Contre-audit effectué avant livraison

Le contre-audit a détecté puis corrigé :

1. un plafond initial de 10 000 crédits qui rendait théoriquement impossible le stage 1 000 avec les coûts par défaut ; plafond technique porté à 20 000 ;
2. une reprise qui aurait changé de date de fin d’un jour à l’autre ; les dates du plan commité sont maintenant réutilisées ;
3. une reprise susceptible d’utiliser l’artefact d’une autre campagne ; comparaison stricte de cinq champs avant restauration ;
4. une campagne qui aurait pu consommer des crédits avant les tests ; `pytest` est exécuté avant la découverte ;
5. un risque de réintroduire le bug CI Railway ; la présence de `cloud_runtime_detected` est contrôlée et les tests de migration sont conservés ;
6. un risque de compter deux fois le budget de découverte ; le budget restant est recalculé depuis `event_discovery_state.json`.

## Verdict consolidé

**GO technique** pour déployer V4.0 et lancer d’abord `dry_run` au stage 30.

**GO conditionnel** pour exécuter le stage 30 lorsque le plan confirme que le budget finance les 30 observations.

**NO-GO** pour passer au stage 100 tant que le rapport du stage 30 ne franchit pas la porte qualité.

**NO-GO** pour toute affirmation de rentabilité ou toute promotion automatique.
