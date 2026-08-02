# Audit multi-rôles V3.2

## Verdict consolidé

| Usage | Verdict |
|---|---|
| Instance privée de recherche | GO |
| Synchronisation quotidienne des cotes | GO avec quota surveillé |
| Backfill historique | GO conditionnel après dry-run et plafond explicite |
| Déclaration d’avantage sur Winamax | NO-GO avant résultats réels suffisants |
| Tennis comme stratégie calibrée | NO-GO |
| Service public multi-utilisateur | NO-GO |
| Placement automatique ou taille de mise | NO-GO |

## 1. Product owner

**Retour.** La V3.1 a prouvé que l’application pouvait être déployée. La V3.2 doit prouver ou réfuter la valeur prédictive.

**Décisions.** Ajout d’un écran « Validation marché », d’un statut `not_run`, du nombre de lignes évaluées, de l’écart de log-loss contre Winamax et de la CLV. L’application ne masque pas l’absence de benchmark.

## 2. Data engineer

**Retour.** Le risque principal est un rapprochement erroné entre les événements The Odds API et les résultats sportifs.

**Décisions.** Le module `event_matching.py` combine noms, aliases et proximité temporelle. Il produit `matched`, `ambiguous` ou `unmatched`. Une ambiguïté est exclue et enregistrée ; elle n’est jamais résolue silencieusement.

**Limite restante.** Le dictionnaire d’aliases est surtout adapté à l’EPL. Les autres compétitions nécessitent leurs propres identifiants canoniques.

## 3. Auditeur anti-fuite

**Constat critique corrigé.** La fonction V3.1 qui construisait les marchés complets groupait initialement par événement et bookmaker. Avec des cotes historiques, cela pouvait fusionner plusieurs snapshots d’un même match.

**Correction.** Le regroupement inclut désormais `requested_snapshot_at` ou `snapshot_time`. Deux snapshots restent deux marchés distincts.

**Règles temporelles.** Une ligne n’est admise que si :

```text
odds_observed_at <= prediction_created_at < commence_time
odds_observed_at < commence_time
```

La closing line n’est jamais injectée dans une prédiction passée.

## 4. Statisticien

**Retour.** Le ROI seul est trop instable.

**Décisions.** Les métriques principales sont log-loss, Brier, RPS, accuracy et ECE. Les comparaisons utilisent des pertes appariées et un bootstrap temporel par blocs. Un rapport sans fold walk-forward reçoit automatiquement `not_evaluable`, même si les métriques descriptives sont bonnes.

**Seuils.** Moins de 200 prédictions reste non évaluable ou exploratoire. Une promotion demande par défaut au moins 500 prédictions évaluées et un intervalle favorable contre Winamax.

## 5. Quant marchés

**Retour.** Le consensus est une baseline plus forte qu’une fréquence historique naïve.

**Décisions.** Quatre approches sont séparées : modèle, Winamax, consensus hors Winamax et blend modèle/consensus. Le poids du blend est choisi uniquement sur la fenêtre d’entraînement de chaque fold.

**Veto.** Aucun poids n’est optimisé sur le fold de test.

## 6. Trader de cotes

**Retour.** Les probabilités implicites doivent être déviguées sur un marché complet.

**Décisions.** Le protocole exige les trois issues 1N2, conserve l’overround, l’heure de mise à jour et le bookmaker. Le consensus utilise la médiane de marchés dévigués et exclut Winamax lorsqu’il sert de comparateur.

## 7. Spécialiste football

**Retour.** Il faut limiter le périmètre avant extension.

**Décisions.** La chaîne complète est livrée d’abord pour `soccer_epl` et le marché `h2h`. Les résultats sont prédits en fenêtre croissante, par groupes de dates identiques, avant révélation des scores du groupe.

## 8. Spécialiste tennis

**Retour.** Le snapshot ATP embarqué est insuffisant pour une validation commerciale ou financière.

**Décisions.** La collecte tennis reste possible, mais la V3.2 ne promeut aucune stratégie tennis. Une reconstruction multi-saisons et une calibration par surface restent nécessaires.

## 9. FinOps API

**Retour.** Le coût historique peut devenir le principal risque opérationnel.

**Décisions.** Le plan calcule le coût avant exécution. Le worker exige `--max-credits`, vérifie le coût unitaire avant chaque appel, journalise le coût réel et compte zéro crédit pour une réponse issue du cache. Les résultats sont écrits par fragments pour permettre la reprise.

## 10. SRE / DevOps

**Retour.** Un backfill ne doit pas bloquer le web ni être lancé en pre-deploy.

**Décisions.** Trois rôles de service : web, cron courant et worker historique. `railway.worker.toml` ne redémarre pas automatiquement. Le cron récupère les cotes puis les résultats récents.

**Limite restante.** L’environnement de génération n’a pas construit l’image Docker ni exécuté un worker sur un vrai projet Railway.

## 11. Sécurité

**Retour.** Une tâche historique ne doit pas élargir l’exposition de la clé.

**Décisions.** Clé uniquement en variable serveur, hôte API figé, paramètres tokenisés, cache expurgé, erreurs sans URL secrète, endpoints d’administration sous authentification et CSRF pour les écritures.

**Limite restante.** Les artefacts Joblib reposent toujours sur Pickle ; ils ne doivent jamais être chargés depuis une source non maîtrisée.

## 12. QA

**Résultats.** 59 tests réussis et 85,44 % de couverture globale. Les tests V3.2 couvrent : séparation des snapshots, veto temporel, matching d’identités, folds, absence de promotion sans folds, scores récents, nouvelles tables, endpoints et configurations worker.

## 13. Conformité et jeu responsable

**Retour.** Une validation meilleure ne doit pas devenir une incitation à parier davantage.

**Décisions.** Aucune taille de mise, aucun objectif quotidien, aucune martingale, aucune connexion Winamax et aucune prise de pari automatique. `Aucun pari retenu` reste une sortie normale.

## 14. Red team

### Risques corrigés

1. Mélange de snapshots historiques.
2. Possibilité théorique de promouvoir un rapport sans fold.
3. Plafond runtime calculé avec un coût fixe de dix crédits, insuffisant pour plusieurs marchés ou groupes de bookmakers.
4. Résultats récents non intégrés au cycle cloud.

### Risques ouverts

1. Pas de benchmark historique réel dans l’archive.
2. Pas de migration Alembic ; `create_all` ajoute les tables mais ne gère pas les modifications complexes de schéma.
3. Matching hors EPL encore incomplet.
4. Horaires exacts parfois absents des résultats Football-Data.
5. Aucune restauration PostgreSQL testée.
6. Aucune preuve de rentabilité et aucune garantie que le modèle battra le marché.

## Conclusion

La V3.2 est une chaîne de preuve, pas une preuve déjà obtenue. Elle est conçue pour permettre un résultat négatif honnête. La prochaine décision dépend exclusivement du benchmark réel : V3.3 Performance si l’avantage tient, ou V3.3 Rebuild si Winamax et le consensus restent meilleurs.
