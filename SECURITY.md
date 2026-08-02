# Sécurité — V3.3

## Secrets

`THE_ODDS_API_KEY`, `APP_PASSWORD`, `APP_SESSION_SECRET` et `DATABASE_URL` doivent rester dans Railway Variables. Ils ne doivent jamais être commités.

La clé fournisseur est transmise uniquement côté serveur et n’est pas écrite dans les fichiers de cache ni dans les réponses du navigateur.

## Accès

- authentification mono-utilisateur ;
- session signée ;
- cookie `Secure` en production ;
- `SameSite=Strict` ;
- protection CSRF ;
- limitation des tentatives de connexion ;
- endpoints API protégés par la même session, hors healthcheck.

## Shadow mode

- aucune exécution de pari ;
- erreurs durables limitées au type d’exception ;
- empreinte de chaque prédiction ;
- enregistrements invalides conservés mais exclus ;
- service cron sans domaine public ;
- arrêt sous un plancher de quota.

## PostgreSQL

La production refuse SQLite. Active les sauvegardes Railway et effectue un test de restauration avant de considérer le service comme durable.

## Artefacts ML

Les fichiers Joblib reposent sur Pickle. Le manifeste SHA-256 détecte une modification accidentelle ou non autorisée des artefacts, mais ne protège pas si un attaquant peut remplacer simultanément l’artefact et le manifeste. Ne charge jamais un artefact externe non fiable.

## CSP

La politique interdit les scripts inline. Ne la relâche pas avec `unsafe-inline` pour contourner une erreur frontend. Les scripts applicatifs sont servis depuis `/static`.

## Limites

- pas de rôles utilisateurs ;
- pas de MFA ;
- pas de WAF ;
- pas d’audit externe ;
- pas de rotation automatique des secrets ;
- pas de validation de restauration exécutée dans cet environnement.
