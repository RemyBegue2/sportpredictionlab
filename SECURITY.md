# Sécurité — V3.1 Cloud

## Secrets

Les secrets attendus sont :

- `APP_PASSWORD` ;
- `APP_SESSION_SECRET` ;
- `THE_ODDS_API_KEY` ;
- `DATABASE_URL`.

Ils doivent être stockés dans le gestionnaire de variables de Railway ou Render. Ils ne doivent pas être placés dans GitHub, le JavaScript, un fichier `.env` versionné ou un message public.

## Authentification

La V3.1 utilise un mot de passe personnel et une session signée. En production :

- `APP_AUTH_REQUIRED=true` ;
- mot de passe d'au moins 12 caractères ;
- secret de session d'au moins 32 caractères ;
- cookie `Secure` ;
- `SameSite=Strict` ;
- durée de session 12 heures ;
- CSRF requis sur les écritures.

Le limiteur de connexion est en mémoire. Il protège une instance unique mais pas plusieurs réplicas.

## Exposition API

`/api/health` et la connexion sont publics. `/api/ready` est protégé. Le healthcheck ne révèle aucun secret. Les endpoints métier, l'OpenAPI et la documentation sont protégés lorsque l'authentification est active.

## The Odds API

- clé exclusivement côté serveur ;
- cache indexé par empreinte sans clé ;
- erreur utilisateur générique ;
- quota exposé, jamais la clé ;
- pas de proxy arbitraire permettant de choisir une URL fournisseur ;
- pas de rafraîchissement forcé depuis l'interface.

## PostgreSQL

- connexion par `DATABASE_URL` ;
- base Render sans liste d'accès IP public dans le Blueprint ;
- snapshots dédupliqués ;
- aucune URL de base renvoyée par l'API ;
- échec de stockage transformé en 503.

## Artefacts ML

Le manifeste SHA-256 détecte une modification accidentelle ou partielle. Joblib/Pickle ne doit jamais charger un fichier fourni par un utilisateur. Si un attaquant peut remplacer à la fois l'artefact et le manifeste, cette protection ne suffit pas. Une version future devrait utiliser un format plus sûr ou une signature externe.

## En-têtes

- Content Security Policy ;
- `X-Content-Type-Options: nosniff` ;
- `X-Frame-Options: DENY` ;
- `Referrer-Policy: no-referrer` ;
- permissions caméra/micro/géolocalisation désactivées.

## Limites restantes

- pas de MFA ;
- pas de comptes individuels ;
- pas de Redis partagé ;
- pas de WAF configuré dans le dépôt ;
- pas de SIEM ou audit log de connexion ;
- pas de scan SAST externe ;
- pas de test d'intrusion ;
- pas de rotation automatisée ;
- pas de migration Alembic.
