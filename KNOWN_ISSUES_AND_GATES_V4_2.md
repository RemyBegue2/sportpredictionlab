# Risques résiduels et portes — V4.2

## Portes bloquantes avant une campagne payante

- préflight `VIABLE` ;
- baseline, stage, budget et version identiques ;
- type d'expérience `french_market_comparison` ;
- intégrité du plan candidat et de la liste d'événements ;
- capacité budgétaire suffisante pour le sur-échantillonnage recommandé ;
- confirmation humaine explicite.

## Portes bloquantes avant le stage 100

- rapport réel stage 30 en `PASS` ;
- zéro fuite temporelle ;
- zéro doublon ;
- zéro collision de matching ;
- couverture fournisseur d'au moins 80 % ;
- matching fiable d'au moins 95 % ;
- couverture de la baseline d'au moins 70 % ;
- au moins 30 événements uniques benchmark-ready ;
- coût total sous le plafond ;
- cohérence GitHub/Railway/API/artefact.

## Risques P1

1. L'intervalle Wilson est un diagnostic conservateur appliqué à un échantillonnage déterministe, pas une preuve formelle issue d'un échantillon aléatoire.
2. Le coût maximal est réservé avant chaque appel, mais le coût réel exact reste connu après la réponse fournisseur.
3. Les identifiants historiques doivent rester stables entre préflight et campagne ; une divergence provoque un arrêt sûr.
4. Les actions GitHub utilisent encore des tags majeurs plutôt que des SHA immuables.
5. Les preuves brutes sont conservées 90 jours dans GitHub Actions.
6. Alembic n'est pas encore introduit pour les évolutions complexes de schéma.
7. Le rate limiter d'authentification reste local au processus.
8. Aucun préflight V4.2 réel n'a été exécuté dans l'environnement de préparation.

## Hors périmètre

- nouveaux championnats ou marchés ;
- extension tennis ;
- optimisation de mise ;
- placement automatique ;
- promotion automatique ;
- conclusion de rentabilité.
