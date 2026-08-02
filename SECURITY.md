# Sécurité V3.7

- Secrets uniquement dans les variables d’environnement Railway/GitHub.
- Aucun secret dans `/api/release`, `/api/model-decision` ou le handoff.
- Les endpoints administratifs restent protégés par l’authentification applicative.
- Le worker historique possède un plafond de crédits, un plan immuable et un redémarrage désactivé.
- Les erreurs de collecte sont journalisées sans clé API.
- Aucune connexion à un compte Winamax et aucun pari automatique.

Le scan de livraison n’a trouvé aucun secret réel. Une référence au nom `THE_ODDS_API_KEY` dans un test a été revue comme faux positif.
