# Audit multi-rôles — Hotfix V4.1.1

Date : 3 août 2026.

## Verdict consolidé

- **Correctif code : GO**
- **Redéploiement Railway : GO contrôlé**
- **Backup GitHub : GO après configuration de `DATABASE_PUBLIC_URL`**
- **Campagne payante : toujours NO-GO tant que le déploiement et le backup ne sont pas validés**

## SRE — cause du healthcheck

Railway interrogeait `/api/ready` sans session. La V4.1.0 avait déplacé la sonde de `/api/health` vers `/api/ready`, mais cette route n'avait pas été ajoutée aux routes publiques de l'auth middleware. En production avec authentification activée, la sonde recevait donc `401` avant même d'atteindre la fonction de readiness.

**Correction :** `/api/ready` est public. Les routes métier restent privées et les écritures restent protégées par session et CSRF.

## Observabilité — absence de logs

Les exceptions d'initialisation de la base et des modèles étaient transformées en état de readiness, mais n'étaient jamais écrites dans stdout. Cela expliquait l'absence d'indice exploitable dans Railway.

**Correction :** logs structurés et sans secret avec le type d'erreur uniquement, par exemple `database startup failed error_type=OperationalError`.

## Data / DBA — cause du backup

L'URL fournie au runner GitHub contient un port vide, de forme `hôte:/base`. SQLAlchemy échouait au parsing avant toute connexion. Une URL Railway privée n'est par ailleurs pas joignable depuis un runner GitHub hébergé.

**Correction :**

- le workflow préfère `DATABASE_PUBLIC_URL` ;
- les guillemets accidentels sont retirés ;
- les schémas PostgreSQL sont normalisés pour psycopg ;
- les ports vides/non numériques sont rejetés avec un message clair ;
- les hôtes `.railway.internal` sont rejetés depuis GitHub Actions ;
- aucun identifiant n'est affiché dans les erreurs.

## Sécurité

Rendre `/api/ready` public est nécessaire pour les sondes de plateforme. La réponse ne contient aucun secret et les erreurs de démarrage stockent seulement le nom de classe de l'exception. Le hotfix ne rend publique aucune route de données ou d'administration.

**Risque résiduel faible :** la readiness expose l'état général et quelques compteurs. Une version future pourra séparer une sonde publique minimale d'un diagnostic détaillé authentifié.

## QA

Validation par quatre lots :

- 37 tests ;
- 41 tests ;
- 58 tests ;
- 25 tests.

Total : **161 réussis, 0 échec**.

Validations complémentaires :

- compilation Python ;
- syntaxe JavaScript ;
- 12 YAML parsés ;
- backup portable SQLite ;
- restauration portable SQLite ;
- erreur d'URL mal formée sans traceback ni identifiants ;
- readiness publique avec API privée toujours protégée ;
- logs de démarrage sans détails sensibles.

## FinOps

Le correctif n'effectue aucun appel fournisseur et ne consomme aucun crédit. Le backup GitHub nécessite l'URL publique PostgreSQL et peut donc utiliser le proxy public Railway. Le chiffrement et la vérification de restauration restent inchangés.

## Action utilisateur indispensable

Dans GitHub, créer le secret `DATABASE_PUBLIC_URL` avec la valeur publique **résolue** affichée par le service PostgreSQL Railway. Elle doit inclure un port numérique. Ne pas utiliser une référence de variable Railway, un hôte `.railway.internal` ou une valeur entre guillemets.

## Ordre de reprise recommandé

1. Configurer `DATABASE_PUBLIC_URL` dans GitHub.
2. Déployer V4.1.1 sur le service web Railway uniquement.
3. Vérifier que `/api/ready` répond `200` et `status=ready`.
4. Relancer le workflow de backup.
5. Déployer ensuite le cron si nécessaire.
6. Reprendre le dry-run du stage 30 seulement après ces validations.
