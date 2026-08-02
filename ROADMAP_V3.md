# Roadmap après V3.3

## P0 — Exploitation du shadow mode

1. Déployer le service `shadow-cron`.
2. Vérifier un cycle complet et le quota.
3. Tester la récupération d’un résultat.
4. Activer et restaurer une sauvegarde PostgreSQL.
5. Observer pendant 14 jours sans mise.

## P0 — Rebuild football

1. Importer plusieurs saisons récentes.
2. Ajouter une identité canonique stable.
3. Réentraîner sur fenêtres croissantes.
4. Calibrer hors entraînement.
5. Comparer modèle, Winamax et consensus.
6. Promouvoir une nouvelle version sans effacer l’ancienne.

## P1 — Qualité marché

- closing line réelle ;
- rapports par horizon ;
- intervalles bootstrap temporels ;
- suivi de calibration ;
- alertes de fraîcheur et dérive.

## P1 — SRE

- alertes sur cron échoué ;
- sauvegarde et restauration automatisées ;
- tableau du quota ;
- politique de rétention ;
- agrégations SQL lorsque le journal dépasse 10 000 lignes.

## V3.4

Deux branches possibles :

- **V3.4 Rebuild**, chemin attendu avec le modèle actuel ;
- **V3.4 Performance**, uniquement après preuve hors temps contre le marché.
