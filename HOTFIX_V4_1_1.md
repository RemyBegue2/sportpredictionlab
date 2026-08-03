# Hotfix V4.1.1 — Railway readiness and database backup URL

## Correctifs

- `/api/ready` est désormais public afin que Railway, Docker et les sondes externes puissent vérifier la readiness lorsque l'authentification applicative est activée.
- Le backup GitHub préfère le secret `DATABASE_PUBLIC_URL`, avec repli temporaire sur `DATABASE_URL`.
- L'outil de backup retire les guillemets accidentels, normalise les schémas PostgreSQL et refuse proprement :
  - les ports vides ou non numériques ;
  - les URL Railway privées depuis GitHub Actions ;
  - les URL mal formées.
- Les erreurs de configuration ne réaffichent jamais les identifiants de connexion.

## Configuration requise dans GitHub

Créer le secret `DATABASE_PUBLIC_URL` avec la valeur résolue fournie par le service PostgreSQL Railway. La valeur doit ressembler à :

`postgresql://utilisateur:mot-de-passe@hote-public:port-numerique/railway`

Ne pas utiliser :

- une URL contenant `${{ ... }}` ;
- un hôte se terminant par `.railway.internal` ;
- une URL avec `hote:/railway` et aucun port.
