# Résultats vérifiés — V3.7 Cloud Control Center

## Validation locale de la source

- **108 tests réussis** ;
- **82,34 % de couverture** sur `sports_predictor` et `webapp.py` ;
- compilation Python réussie ;
- syntaxe JavaScript valide avec Node.js ;
- sept workflows GitHub Actions valides en YAML ;
- fichiers TOML valides ;
- contrat HTML/JavaScript et endpoint `/api/control-center` testés ;
- endpoint public `/api/release` testé avec les garde-fous de sécurité ;
- génération du ZIP de reprise testée sans export de secret.

## Corrections issues de la contre-audit

1. La vérification post-déploiement n’appelle plus un endpoint protégé sans session. Tous les contrôles automatisés nécessaires sont présents dans `/api/release`, qui reste public et minimal.
2. Le rollback ne dépend plus d’un dossier de snapshots ignoré par Git. Il restaure les artefacts et le dataset actif depuis un commit Git connu, puis crée un nouveau commit de restauration.
3. Le petit benchmark possède maintenant trois plafonds durs : 30 événements, 31 appels de découverte et 200 crédits de cotes.
4. Le test Chromium est obligatoire lorsque l’option de vérification navigateur est activée. L’absence de `APP_PASSWORD` bloque le workflow au lieu de produire un faux succès.
5. Le rollback vérifie également l’interface privée après le déploiement.

## Limites de cette validation

- aucun déploiement Railway n’a été déclenché depuis cet environnement ;
- le smoke test Chromium contre le vrai domaine Railway est implémenté, mais il ne peut être exécuté ici sans les secrets et l’accès à la production ;
- aucun crédit The Odds API n’a été consommé ;
- cinq `ResourceWarning` SQLite sont encore émis par d’anciens tests. Ils ne font pas échouer la suite, mais le nettoyage explicite des connexions reste une dette technique ;
- la sauvegarde V3.7 est une sauvegarde logique portable testée par restauration, pas une image physique complète de PostgreSQL.

## Verdict

La V3.7 est prête à être intégrée puis validée sur Railway avec **Deploy production**. Elle rend le parcours normal exploitable depuis le navigateur, sans Python local. Elle ne démontre aucune rentabilité sportive et ne permet aucun pari automatique.
