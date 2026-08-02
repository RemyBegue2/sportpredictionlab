# Mise à niveau V3.5 → V3.6

1. Sauvegarder le dépôt ou créer une branche.
2. Décompresser l’upgrade à la racine.
3. Ne pas remplacer les modèles et données actifs.
4. Pousser le commit :

```bash
git add -A
git commit -m "Upgrade to V3.6 evidence engine"
git push
```

5. Définir `MODEL_VERSION=3.6.0` sur le service web et `shadow-cron`.
6. Déployer le dernier commit sur les deux services.
7. Vérifier :

```text
/api/health
/api/release
/api/model-decision
```

Le premier verdict peut rester `not_evaluable`. Cela signifie qu’il manque des preuves, pas que le déploiement a échoué.
