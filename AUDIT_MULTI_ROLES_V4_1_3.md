# Audit multi-rôles — V4.1.3

## Incident SRE

Le service Railway a été déployé, mais GitHub Actions a échoué sur la récupération du flux de logs Railway. Le workflow confondait donc l'observabilité du build avec le résultat réel du déploiement.

## Arbitrage

- **SRE** : utiliser le mode détaché pour éviter qu'un canal de logs indisponible invalide le déploiement.
- **QA** : conserver une vérification forte de la version et du commit après le déploiement.
- **Sécurité** : ne pas contourner les contrôles de readiness ou d'intégrité.
- **Produit** : corriger uniquement le mécanisme de livraison, sans modifier les prédictions ou les données.

## Correction retenue

`railway up --detach` dans tous les workflows, suivi de la vérification publique exacte du web. Aucun `railway up --ci` ne subsiste.

## Audit evidence

La campagne CMP-7DD3582E9007344F9F9F500A est techniquement saine mais statistiquement inutilisable pour le stage 30 : 6 événements benchmark-ready et 23,3 % de couverture Winamax/consensus contre 96,7 % pour Pinnacle.

## Décision

- V4.1.3 : GO.
- Relance du workflow de déploiement : GO.
- Reprise de la même campagne evidence : NO-GO.
- Stage 100 : NO-GO.
- Développement d'un coverage preflight : prochaine priorité.
