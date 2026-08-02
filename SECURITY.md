# Sécurité V3.2

## Protections actives

- authentification privée en production ;
- sessions signées, cookie Secure et SameSite strict ;
- CSRF sur les écritures ;
- clé The Odds API uniquement côté serveur ;
- hôte fournisseur figé pour limiter le SSRF ;
- paramètres API validés ;
- clé exclue des empreintes, caches, réponses et erreurs ;
- CSP, anti-framing, nosniff et politique de permissions ;
- manifeste SHA-256 avant chargement des modèles ;
- PostgreSQL obligatoire en production ;
- plafond explicite pour les backfills historiques.

## Worker historique

Le worker ne doit jamais recevoir une commande arbitraire depuis l’interface web. Son plan est un fichier contrôlé et son budget est une variable serveur. Les fragments historiques restent privés et ne sont pas exposés par l’API.

## Risques restants

- Joblib repose sur Pickle. Ne jamais charger un artefact non maîtrisé.
- `Base.metadata.create_all` ne fournit pas un historique de migrations ; adopter Alembic avant modifications complexes.
- La restauration PostgreSQL n’a pas été testée dans cet environnement.
- Une personne ayant accès au projet Railway peut lire ou remplacer les variables non scellées.
- Une dépendance compromise reste un risque ; utiliser les mises à jour et scanners du dépôt.

## Secrets

Ne jamais placer dans Git :

```text
THE_ODDS_API_KEY
APP_PASSWORD
APP_SESSION_SECRET
DATABASE_URL
```
