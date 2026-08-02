# Sécurité V3.4

- Clé The Odds API uniquement dans les variables serveur.
- Authentification et CSRF conservés.
- CSP stricte conservée.
- Artefacts actifs vérifiés par SHA-256 avant chargement.
- Verrou consultatif PostgreSQL contre les cycles concurrents.
- Erreurs persistées limitées aux types d'exception.
- Téléchargements de saisons limités en taille, avec timeout et écriture atomique.
- Le workflow de reconstruction n'utilise aucun secret fournisseur.

## Limite connue

Joblib repose sur Pickle. Le manifeste détecte une modification accidentelle ou non autorisée des fichiers, mais ne protège pas si un attaquant peut remplacer simultanément l'artefact et son manifeste. Les artefacts doivent provenir du dépôt et du workflow contrôlés.
