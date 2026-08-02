# Changelog

## 3.2.1

- Corrige le crash `ci[0].toFixed` lorsqu'aucun benchmark historique n'a encore été exécuté.
- Empêche une erreur de rendu secondaire de transformer le badge de santé en `API indisponible`.
- Ajoute un cache-busting du JavaScript et des tests de non-régression.

## 3.2.0

- ajout du benchmark historique modèle–Winamax–consensus ;
- folds chronologiques et blend train-only ;
- audit temporel et bootstrap par blocs ;
- matching événement/résultat avec veto d’ambiguïté ;
- séparation des snapshots historiques ;
- tables résultats, benchmark, qualité et backfill ;
- worker Railway reprenable et budgété ;
- synchronisation des scores récents ;
- écran Validation marché ;
- 59 tests, couverture globale 85,44 %.

## 3.1.2

- correction robuste du chemin d’import Python dans Railway.
