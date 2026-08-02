# Mise à niveau V3.6 → V3.7 sans Python local

## Fichiers à préserver

Ne pas remplacer ni supprimer :

```text
artifacts/football_model.joblib
artifacts/tennis_model.joblib
artifacts/metrics.json
artifacts/artifact_manifest.json
artifacts/fresh_rebuild_report.json
artifacts/release_manifest.json
data/real/
```

L’archive d’upgrade fournie exclut ces fichiers.

## Installation

1. Décompresser l’archive V3.7.
2. Copier son contenu à la racine du dépôt GitHub en acceptant le remplacement.
3. Vérifier que `.github/workflows/` contient les sept workflows V3.7.
4. Créer un commit nommé par exemple `Upgrade to V3.7 cloud control center`.

## Déploiement

Dans GitHub :

```text
Actions
→ Deploy production
→ Run workflow
```

Conserver les trois options activées. Le workflow exécute lui-même les tests, la génération du manifeste, le déploiement Railway et les contrôles post-déploiement.

## Vérification

Le résumé du workflow doit confirmer :

```text
version 3.7.0
commit attendu = commit Railway
hash du modèle attendu = hash Railway
interface Chromium chargée sans erreur
```

L’interface doit afficher **Pilotage → Centre de contrôle**.
