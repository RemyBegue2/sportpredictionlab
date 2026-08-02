# Audit multi-rôles V3.5 — Operational Evidence & Model Registry

## Verdict global

- **GO** : application privée, shadow mode, registre des releases, preuve post-déploiement et handoff.
- **GO conditionnel** : rollback d’artefacts après test sur une copie et restauration de backup vers une base vide.
- **NO-GO** : service public multi-utilisateur, placement automatique, tailles de mise et affirmation de rentabilité.
- **NON VÉRIFIÉ ICI** : restauration d’une sauvegarde PostgreSQL managée Railway et déploiement réel depuis GitHub Actions.

## Product Owner

### Retour

L’utilisateur ne doit plus déduire la version déployée à partir d’un badge ou d’un workflow vert. Une page unique doit montrer la version, le commit, le modèle, le dataset, l’intégrité et les incidents.

### Décisions intégrées

- cartes « Release active », « Modèle football » et « Contrat de déploiement » ;
- endpoint consolidé `/api/system/status` ;
- chargement indépendant des sections frontend avec `Promise.allSettled` ;
- bouton de vérification sans relancer un rebuild.

## Data Engineer

### Retour

Un modèle ne peut pas être repris correctement si le hash du dataset, le cutoff et l’artefact ne sont pas reliés.

### Décisions intégrées

- `artifacts/release_manifest.json` ;
- SHA-256 des modèles et fichiers frontend critiques ;
- dataset hash, nombre de lignes et cutoff lorsqu’ils existent ;
- registre de releases PostgreSQL ;
- export JSON/Markdown de continuité.

## Auditeur anti-fuite

### Retour

Le registre opérationnel ne doit jamais réécrire les anciennes prédictions ni changer leur version de modèle.

### Décisions intégrées

- aucune migration destructive des prédictions shadow ;
- métriques groupées par `model_id`, `model_version` et horizon ;
- rollback limité aux artefacts actifs, jamais à l’historique de prédictions ;
- closing line toujours réservée à l’évaluation.

## Statisticien

### Retour

Mélanger les observations de plusieurs modèles ou horizons rend les métriques trompeuses.

### Décisions intégrées

- `by_model_horizon` dans le résumé shadow ;
- horizon principal conservé uniquement pour l’affichage synthétique ;
- aucune promotion automatique sur ROI isolé ;
- tailles d’échantillon et maturité conservées.

## Ingénieur ML

### Retour

Le statut d’un modèle ne doit pas être recalculé à chaque redémarrage de l’application.

### Décisions intégrées

- cycle de vie explicite et transitions auditées ;
- un redémarrage met à jour les métriques mais préserve le statut existant ;
- un seul modèle `active` par sport ;
- activation d’un nouveau modèle dégrade explicitement l’ancien ;
- historique des transitions avec motif et acteur.

## SRE / DevOps

### Retour

Un workflow vert n’est pas une preuve de déploiement. Le contrôle doit interroger le conteneur réellement exposé.

### Décisions intégrées

- `/api/release` public, minimal et sans secret ;
- script `post_deploy_verify.py` avec retries ;
- comparaison version, commit, hash du modèle et intégrité ;
- étape GitHub Actions facultative activée par `APP_PUBLIC_URL` ;
- registre `running/previous` des releases observées.

## Sécurité

### Retour

La preuve de release publique ne doit révéler aucune configuration sensible. Les transitions de modèles doivent rester privées et protégées contre le CSRF.

### Décisions intégrées

- aucune clé, URL de base, cookie ou mot de passe dans le manifeste ;
- `/api/release` ne renvoie que des identifiants techniques non secrets ;
- `/api/system/status` et les écritures modèle restent authentifiés ;
- validation stricte des transitions ;
- export de handoff basé sur une liste blanche.

## QA

### Retour

Les incidents précédents provenaient de contrats implicites entre HTML, JavaScript, API et artefacts.

### Décisions intégrées

- tests du manifeste et des hashes ;
- tests du registre et de l’unicité du modèle actif ;
- tests de snapshot/rollback ;
- tests du backup/restore sur SQLite ;
- tests des endpoints release/system ;
- contrats frontend existants conservés ;
- **91 tests réussis**.

## Trader de cotes

### Retour

La traçabilité du modèle ne doit pas faire oublier la traçabilité du prix.

### Décisions intégrées

- aucune modification des exigences de marché complet et d’horodatage ;
- métriques par horizon ;
- le modèle actif, la cote observée et la décision restent liés dans chaque prédiction shadow.

## Responsable jeu responsable

### Retour

Une meilleure exploitation ne doit pas transformer l’application en système d’incitation.

### Décisions intégrées

- aucune taille de mise ;
- aucune connexion Winamax ;
- aucun placement automatique ;
- abstention conservée ;
- rendement fictif clairement secondaire et normalisé.

## Risques restants

1. La copie locale de cette release ne contient pas forcément les artefacts frais créés dans le dépôt réel de l’utilisateur.
2. Le post-déploiement automatique nécessite des identifiants Railway et la variable GitHub `APP_PUBLIC_URL`.
3. Le backup portable est testé sur SQLite, mais une restauration PostgreSQL managée doit encore être répétée sur une base de test Railway.
4. Les observations shadow peuvent rester insuffisantes pour toute conclusion statistique.
5. Le tennis reste non calibré.
