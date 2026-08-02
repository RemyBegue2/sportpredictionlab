# Audit multi-rôles contradictoire — V3.1 Cloud

## Verdict exécutif

- **GO** : application privée de recherche, accessible par URL, sur une seule instance.
- **GO conditionnel** : synchronisation planifiée des cotes après contrôle du quota et validation d'un premier run.
- **NO-GO** : accès public sans authentification, service multi-utilisateur, promesse de rentabilité, recommandations de mise ou placement automatique.
- **NO-GO statistique** : aucune conclusion de supériorité contre Winamax ou la closing line avant le benchmark V3.2.

## 1. Product owner

### Retour

La V3 locale imposait l'installation de Python et le lancement d'un serveur. Le produit devait devenir utilisable depuis un téléphone, sans masquer les abstentions ni les erreurs de fraîcheur.

### Changements intégrés

- interface accessible par URL ;
- authentification personnelle ;
- statut cloud visible ;
- historique des prédictions ;
- page « Paris du jour » alimentée par PostgreSQL ;
- shortlist vide acceptée ;
- cote ancienne reclassée `à actualiser`.

### Réserve

L'interface ne permet pas encore de filtrer l'historique par ligue, décision ou date.

## 2. DevOps / platform engineer

### Retour

Un simple frontend Netlify ne suffit pas à exécuter FastAPI, CatBoost, PostgreSQL et un collecteur périodique dans la même architecture.

### Changements intégrés

- Dockerfile avec utilisateur non-root ;
- port dynamique `${PORT}` ;
- `railway.toml` pour le service web ;
- `railway.cron.toml` pour le collecteur ;
- `render.yaml` pour un Blueprint web + DB + cron ;
- migration de schéma avant démarrage ;
- healthcheck minimal séparé de la readiness.

### Réserve

Aucun moteur Docker n'était disponible dans l'environnement d'audit. La construction réelle de l'image reste à vérifier sur la plateforme.

## 3. SRE

### Retour

Une API qui répond ne signifie pas que les modèles ou la base fonctionnent.

### Changements intégrés

- `/api/health` : liveness sans dépendance lourde ;
- `/api/ready` : modèles, manifeste, base et configuration ;
- politique de redémarrage ;
- journal des runs du cron ;
- erreur 503 si une prédiction ne peut pas être auditée en base ;
- script de smoke test distant.

### Réserves

- pas encore d'alerte automatique ;
- pas de test de restauration de sauvegarde ;
- pas de SLO de disponibilité ;
- pas de monitoring de latence ou de dérive.

## 4. Data engineer

### Retour

Les JSON locaux et le cache `/tmp` ne constituent pas un stockage de référence cloud.

### Changements intégrés

- schéma SQLAlchemy PostgreSQL/SQLite ;
- événements séparés des snapshots ;
- horodatages `observed_at` et `fetched_at` ;
- contrainte anti-doublon ;
- journal des prédictions et synchronisations ;
- `DATABASE_URL` compatible Railway/Render ;
- aucune donnée durable dépendante du disque du cron.

### Réserves

- `create_all` initialise le schéma mais ne remplace pas un système de migrations versionnées ;
- pas encore de politique de rétention ;
- pas de sauvegarde exportée et testée ;
- pas de résolveur d'identités canonique multi-ligues.

## 5. Security engineer

### Retour

Une URL publique avec une clé fournisseur et un endpoint d'actualisation peut être abusée pour consommer le quota ou lire les analyses.

### Changements intégrés

- mot de passe obligatoire en production ;
- secret de session distinct ;
- cookie `Secure` et `SameSite=Strict` en cloud ;
- CSRF sur POST/PUT/PATCH/DELETE ;
- limite de tentatives de connexion ;
- CSP, anti-frame, nosniff et referrer policy ;
- secrets fournis par variables d'environnement ;
- aucune clé dans les réponses, le cache ou les fichiers de déploiement ;
- documentation API protégée par la même session.

### Réserves

- mot de passe unique, pas de comptes individuels ni MFA ;
- rate limiter en mémoire, non partagé entre réplicas ;
- pas de WAF ni de journal de connexion durable ;
- pas de rotation automatisée des secrets ;
- Joblib reste un format de sérialisation à risque si un attaquant remplace les artefacts et leur manifeste.

## 6. Quant / statisticien

### Retour

Le passage au cloud ne doit pas être confondu avec une amélioration du modèle.

### Changements intégrés

- version du modèle enregistrée avec chaque prédiction ;
- historique permettant une future comparaison hors échantillon ;
- aucune prédiction live après le début du match ;
- conservation de la marge, de la probabilité déviguée et de l'EV robuste ;
- abstention obligatoire pour le tennis non calibré ;
- aucune revendication de ROI.

### Réserves

- benchmark historique réel non exécuté ;
- football limité à un petit snapshot EPL ;
- paramètres Dixon–Coles et calibration précédemment proches des bornes ;
- pas de nested calibration ni refit final complet ;
- aucune preuve de CLV positive.

## 7. Trader de cotes

### Retour

Un verdict stocké ne doit pas rester positif lorsque la cote a vieilli.

### Changements intégrés

- heure du bookmaker persistée ;
- fraîcheur recalculée au moment de l'affichage ;
- downgrade automatique vers `à actualiser` ;
- marché complet obligatoire ;
- retrait de la marge ;
- consensus hors Winamax ;
- blocage des événements commencés.

### Réserves

- pas encore de graphique d'ouverture/closing ;
- pas de détection de changement de limite ou de marché suspendu ;
- pas de mesure de délai entre API et bookmaker visible.

## 8. FinOps / quota manager

### Retour

Une application publique ne doit pas permettre à chaque affichage de dépenser des crédits.

### Changements intégrés

- cache fournisseur ;
- cron contrôlé ;
- football seulement par défaut ;
- tennis explicitement opt-in ;
- suivi du coût et du quota dans les runs ;
- endpoint de devis historique ;
- aucun rafraîchissement forcé depuis l'interface publique.

### Réserves

- pas encore de plafond quotidien persistant ;
- pas d'alerte de quota bas ;
- les coûts Railway/Render et The Odds API restent à valider par l'utilisateur.

## 9. QA engineer

### Retour

Il fallait tester autre chose que le calcul probabiliste.

### Changements intégrés

La suite couvre :

- sécurité de configuration production ;
- session et CSRF ;
- persistance et déduplication ;
- historique de prédictions ;
- readiness ;
- expiration des cotes ;
- parsing des fichiers Railway/Render ;
- absence de secret dans le Dockerfile ;
- flux fournisseur simulés ;
- moteurs football, tennis et marché.

### Résultat

**41 tests réussis**, plus un smoke test HTTP authentifié complet et un rendu Chromium sans erreur console.

### Réserves

- aucun test réel PostgreSQL ;
- aucun build Docker ;
- aucun test de charge ;
- rendu de l’aperçu vérifié avec Chromium local ; aucun test end-to-end sur une plateforme distante ;
- pas d'audit d'accessibilité complet.

## 10. Responsable conformité et jeu responsable

### Retour

L'hébergement augmente la portée apparente du service et donc le risque de le présenter comme un conseil garanti.

### Changements intégrés

- application privée ;
- aucune connexion au compte Winamax ;
- aucune exécution automatique ;
- aucune taille de mise ;
- aucune martingale ou combiné optimisé ;
- erreurs et abstentions visibles ;
- avertissement de vérification directe des prix ;
- données brutes fournisseur non exposées comme produit autonome.

### Réserve

Avant toute ouverture à d'autres utilisateurs ou monétisation, une revue juridique spécifique des licences, conditions du fournisseur et obligations locales reste nécessaire.

## 11. Red team

### Scénarios testés conceptuellement

1. **Vol de clé dans le navigateur** : bloqué par le backend serveur.
2. **CSRF déclenchant une collecte** : actions d'écriture protégées ; les slates live restent en GET mais ne forcent pas le cache.
3. **Brute force du mot de passe** : limité sur une instance, insuffisant en multi-réplicas.
4. **Cote positive devenue ancienne** : reclassée à l'affichage.
5. **Base indisponible** : readiness en erreur et prédiction non livrée comme auditée.
6. **Match commencé** : analyse pré-match bloquée.
7. **Double insertion du même snapshot** : contrainte et contrôle applicatif.
8. **Fuite de secret dans une erreur** : erreurs résumées par type dans le cron et messages génériques dans l'API.

## Arbitrage final

La V3.1 atteint son objectif produit : ouvrir une URL, se connecter et utiliser l'application sans installation locale. Elle ne franchit pas encore le seuil d'une plateforme publique ou d'une stratégie de pari validée.

La prochaine version doit être **V3.2 Benchmark réel** : collecte historique contrôlée, cinq folds chronologiques, modèle contre Winamax et consensus, CLV, calibration, intervalles et règle de sélection gelée.
