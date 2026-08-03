# Sports Prediction Lab — point de reprise V4.2

## État préparé

- Version du code : **4.2.0 — Coverage-Aware Evidence Planning**.
- Exploitation : GitHub Actions + Railway, sans Python local.
- Nouveau workflow préalable : **Estimate evidence coverage**.
- Workflow de campagne : **Run evidence campaign**.
- Stages : 30, 100, 300 et 1 000 événements benchmark-ready.
- Baselines exécutables de la campagne principale : `consensus` ou `winamax`.
- `pinnacle` est uniquement une expérience de disponibilité fournisseur séparée.

## Garanties V4.2

- préflight plafonné et reprenable avant le backfill complet ;
- verdict `VIABLE/RISKY/NOT_VIABLE` ;
- aucune campagne payante sans préflight `VIABLE` exact ;
- sur-échantillonnage calculé pour atteindre le stage en observations évaluables ;
- plan candidat immuable avec hashes des sondes, preuves et événements ;
- sélection fondée uniquement sur la disponibilité et la chronologie, jamais sur les résultats ou métriques du modèle ;
- payload fournisseur vide traité proprement comme non viable ;
- déploiements Railway détachés puis vérifiés par `/api/ready`, version, commit et hash de modèle.

## Résultat réel à conserver

La campagne précédente a démontré une bonne couverture Pinnacle mais seulement environ 23 % de couverture Winamax/consensus français. Elle reste `HOLD` et ne doit pas être reprise. Le stage 100 reste interdit.

## Prochaine action sûre

1. Déployer V4.2.0.
2. Vérifier `/api/ready`, `/api/release` et `/api/coverage-preflight`.
3. Lancer **Estimate evidence coverage** avec un petit plafond.
4. Lire le verdict et la matrice de couverture.
5. Lancer une campagne payante uniquement si le préflight est `VIABLE` et après approbation humaine.

Ne jamais réduire les seuils après observation des données, promouvoir automatiquement un modèle, recommander une mise ou placer un pari.
