# Model Card — Sports Prediction Lab V3.3

## Usage prévu

Recherche privée sur des probabilités pré-match football et tennis, comparaison avec des cotes et validation en shadow mode.

## Usage interdit

- placement automatique ;
- conseil de mise ;
- garantie de gain ;
- crédit ou décision financière ;
- service commercial fondé sur les données tennis embarquées.

## Football

**Marché :** 1N2 pré-match, Premier League.

**Données embarquées :** 90 matchs du 11 août au 23 octobre 2023.

**Méthodes :** Elo, variables séquentielles, Poisson, Dixon–Coles et composante ML évaluée. Le poids ML final du snapshot est nul.

**Forces :** traitement groupé des timestamps, probabilités normalisées, backtest chronologique, journal shadow.

**Limites critiques :** échantillon réduit, données anciennes, aucune information d’effectif 2026, paramètres instables sur petit échantillon.

**Statut :** `degraded` pour les fixtures dépassant `MODEL_MAX_AGE_DAYS`. Les candidats marché sont alors bloqués.

## Tennis

**Méthode servie :** Elo global et surface.

**Données :** 32 matchs et seulement deux timestamps de tournoi.

**Statut :** `experimental`, non calibré. Aucune sélection opérationnelle.

## Shadow mode

Les observations sont immuables, horodatées et séparées par horizon. Une empreinte SHA-256 permet de détecter un changement de contenu. Les violations temporelles sont mises en quarantaine.

## Critères de promotion d’un nouveau modèle

- données récentes et multi-saisons ;
- folds chronologiques ;
- calibration hors entraînement ;
- meilleure performance qu’une baseline naïve ;
- comparaison contre Winamax et consensus ;
- stabilité sur plusieurs périodes ;
- modèle non périmé ;
- au moins plusieurs centaines d’observations shadow valides.
