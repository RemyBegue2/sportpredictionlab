# Résultats vérifiés — V2.2

## Exécution

- Entraînement du snapshot football avec split groupé par timestamp.
- Artefact tennis Elo-only, faute de calibration honnête possible.
- Backtest football externe par lot de date.
- Moteur de comparaison Winamax 2-way et 3-way.
- **24/24 tests réussis**.
- Couverture : **88 %** globale, **92 %** sur `backtest.py`, **88 %** sur `betting.py`.

## Football

### Test interne — 90 matchs EPL 2023-24

- Test : 20 matchs.
- Log-loss : 0,9399.
- Baseline naïve : 1,1159.
- Accuracy : 60,0 %.
- ECE : 0,0781.
- Poids ML final : 0,00.

### Backtest externe — 30 prédictions

- Log-loss : 0,9872.
- Baseline : 1,0740.
- Écart moyen : -0,0868.
- IC bootstrap en blocs : [-0,1094 ; -0,0176].
- Accuracy : 53,3 %.
- ECE : 0,1767.

Ce résultat est un signal technique, pas une validation économique.

## Tennis

- 32 lignes réelles, seulement 2 dates de tournoi.
- Évaluation leakage-safe impossible.
- Mode livré : Elo symétrique non calibré.
- Toute analyse de cote force l'abstention.

## Paris du jour — 2 août 2026

- Événements revus : 2.
- Candidats recherche : 0.
- Abstentions : 2.
- ATP Fritz–Jodar : joueur absent du snapshot, modèle non calibré, cote Winamax non vérifiée.
- WTA Pegula–Eala : aucun modèle WTA, cote Winamax non vérifiée.

## Règle de promotion

Une sélection ne peut devenir “candidat recherche” que si :

1. le marché complet est renseigné ;
2. la cote a moins de 60 minutes ;
3. le modèle est calibré ;
4. l'edge face au marché dévigé est au moins 3 points ;
5. l'EV reste au moins +2 % après réduction conservatrice de la probabilité.
