# Audit multi-rôles V3.7 — Cloud Control Center

## Contexte

La V3.6 était techniquement exploitable, mais plusieurs procédures demandaient encore des commandes Python locales. L’utilisateur n’a pas Python sur son ordinateur et a choisi Railway et GitHub précisément pour éviter cette dépendance.

## Product Owner

**Retour :** les fonctions existent, mais l’utilisateur doit encore comprendre des scripts et des fichiers techniques.

**Décision appliquée :** création d’un centre de contrôle unique. Chaque état contient un diagnostic, une action en français et le nom exact du workflow GitHub à lancer.

## Utilisateur non-développeur

**Retour :** aucune commande locale ne doit faire partie du parcours normal.

**Décision appliquée :** `local_python_required=false` dans l’API et dans le pack de reprise. Déploiement, vérification, benchmark, sauvegarde, rollback et handoff sont accessibles dans l’onglet Actions.

## SRE / exploitation

**Retour :** un workflow vert ne prouve pas que Railway sert le bon code.

**Décision appliquée :** le déploiement vérifie `/api/release` après Railway et compare version, commit et SHA-256 du modèle. Le run échoue en cas de divergence.

## QA frontend

**Retour :** les tests unitaires ne détectent pas tous les défauts visibles dans le navigateur.

**Décision appliquée :** ajout d’un smoke test Chromium authentifié. Il contrôle le badge de version, le chargement du centre de contrôle, les erreurs JavaScript et les erreurs de console.

## DevOps Railway

**Retour :** `railway up` ne transporte pas nécessairement le dossier `.git`, ce qui peut rendre le commit d’exécution inconnu.

**Décision appliquée :** le manifeste généré avant le déploiement contient le commit GitHub. L’application l’utilise comme preuve de secours lorsque le runtime ne peut pas exécuter `git rev-parse`.

## Data Engineer

**Retour :** le backfill doit être plafonné, reprenable et journalisé en PostgreSQL.

**Décision appliquée :** le workflow historique conserve les limites V3.6, bloque au-delà de 30 événements et publie les plans, checkpoints et fichiers de preuve comme artefacts GitHub.

## FinOps API

**Retour :** l’utilisateur doit savoir clairement quand des crédits seront consommés.

**Décision appliquée :** `plan_only` ne fait aucun appel API. `execute_sample` exige la chaîne exacte `EXECUTE_SAMPLE`, un plafond de découverte et un plafond de crédits de cotes.

**Limite assumée :** les appels de découverte et les appels de snapshots ont deux plafonds séparés. Le résumé GitHub les affiche distinctement.

## Statisticien

**Retour :** simplifier l’exploitation ne doit pas assouplir les portes statistiques.

**Décision appliquée :** aucun changement aux critères de la V3.6. `promotion_review` reste une demande de revue humaine, jamais une activation automatique.

## Auditeur anti-fuite

**Retour :** un workflow cloud ne doit pas contourner les contrôles temporels.

**Décision appliquée :** les scripts historiques existants restent la seule voie d’écriture. Les timestamps, hashes de plan, checkpoints et quarantaines temporelles sont conservés.

## Sécurité

**Retour :** multiplier les workflows augmente la surface de secrets et d’actions destructrices.

**Décision appliquée :** permissions GitHub minimales, confirmations exactes pour les actions coûteuses/destructrices, secrets uniquement dans GitHub Actions, pack de reprise filtré et aucune valeur sensible dans les résumés.

## Responsable sauvegarde

**Retour :** une sauvegarde non restaurée n’est pas une preuve de reprise.

**Décision appliquée :** le workflow de sauvegarde restaure automatiquement l’export dans une base temporaire avant de publier l’artefact.

## Responsable jeu responsable

**Retour :** une interface plus facile ne doit pas rendre le pari plus facile.

**Décision appliquée :** le centre de contrôle gère la plateforme, pas les mises. Les interdictions de pari automatique, de staking et de connexion au compte restent explicites dans l’API et l’interface.

## Verdict contradictoire

- **GO** pour le déploiement V3.7.
- **GO conditionnel** pour un petit lot historique après lecture du plan et des plafonds.
- **NO-GO** pour un backfill large avant validation du matching, du coût réel et de la qualité temporelle.
- **NO-GO** pour toute affirmation de rentabilité ou automatisation de pari.

## Contre-audit final avant livraison

### Red Team authentification

**Constat :** la première implémentation de la vérification post-déploiement appelait `/api/model-decision`, endpoint protégé par la session privée. Avec `APP_AUTH_REQUIRED=true`, le workflow aurait reçu une réponse 401 après un déploiement pourtant correct.

**Correction :** le contrat public minimal `/api/release` expose maintenant uniquement les drapeaux nécessaires (`automatic_model_promotion=false`, `profitability_claim=false`, `automatic_bet_placement=false`). Le vérificateur n’appelle plus aucune route privée.

### SRE rollback

**Constat :** la première implémentation supposait la présence de snapshots dans un dossier ignoré par Git. Un runner GitHub neuf ne les aurait pas trouvés.

**Correction :** le rollback prend désormais un commit Git connu comme source de vérité. Il restaure les artefacts et le dataset actif depuis ce commit, teste, crée un nouveau commit de restauration, déploie et vérifie l’interface.

### FinOps hostile

**Constat :** les valeurs par défaut étaient prudentes, mais un utilisateur pouvait augmenter librement les plafonds d’appels et de crédits dans le formulaire GitHub.

**Correction :** le workflow refuse désormais plus de 30 événements, 31 appels de découverte ou 200 crédits de cotes, indépendamment des valeurs saisies.

### QA production

**Constat :** un test Chromium demandé pouvait être ignoré silencieusement lorsque `APP_PASSWORD` manquait, laissant le workflow vert après la seule vérification API.

**Correction :** quand `verify_browser=true`, l’absence du secret bloque le workflow. Le test reste désactivable explicitement pour un diagnostic API ciblé, jamais implicitement.

## Retour consolidé des rôles

- **Product Owner : GO**, car l’action suivante est visible et nomme le workflow exact.
- **Utilisateur non-développeur : GO**, aucun script local n’est requis dans le parcours normal.
- **SRE : GO conditionnel**, sous réserve du premier run réel Railway et Chromium.
- **Sécurité : GO**, avec secrets GitHub, permissions limitées et sauvegarde chiffrée ; la phrase de chiffrement doit rester hors dépôt.
- **Data Engineer : GO pour le lot court**, NO-GO pour une collecte longue tant que le worker dédié n’est pas validé.
- **FinOps : GO**, grâce aux plafonds durs et à la confirmation explicite.
- **Statisticien : aucun changement de verdict**, le modèle reste non démontré face au marché.
- **Responsable jeu responsable : GO**, aucune mise, aucun pari et aucune promotion automatique.
