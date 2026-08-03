# Sports Prediction Lab — point de reprise V4.4.0

## État préparé

- Version : **4.4.0 — Dual-Sport ROI Lab**.
- Produit : football et tennis du jour, probabilités, signaux shadow et bankrolls simulées.
- Modèle football : opérationnel pour la recherche.
- Modèle tennis : Elo non calibré ; signal bloqué jusqu'à preuve spécifique suffisante ou méta-modèle validé.
- Dépenses live : manuelles, plafonnées et conditionnées au shadow.
- Evidence historique : désactivée.

## Première action

1. Déployer V4.4.0.
2. Vérifier `/api/ready`, `/api/release`, `/api/daily/slate` et `/api/research-lab`.
3. Confirmer que le dashboard fonctionne sans appel fournisseur.
4. Pour une expérience limitée, suivre `OPERATIONS_RUNBOOK_V4_4.md` avec un plafond de trois crédits.
5. Régler les résultats puis lancer l'optimisation zéro crédit.

## Règles

- un signal est expérimental, pas une recommandation ;
- aucune mise ou exécution automatique ;
- aucune modification des seuils après observation sans nouvelle version ;
- moins de 30 résultats : politique ROI non évaluable ;
- moins de 60 résultats : méta-modèle non évaluable ;
- aucun ROI historique n'est une promesse de rentabilité.
