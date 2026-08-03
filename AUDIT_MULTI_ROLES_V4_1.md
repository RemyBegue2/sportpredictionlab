# Audit multi-rôles — V4.1 Decision Integrity & Resumable Operations

## Verdict consolidé

- **Code V4.1 : GO**
- **Pull request et déploiement contrôlé : GO**
- **Dry-run du stage 30 : GO après déploiement vérifié**
- **Campagne payante : revue humaine obligatoire**
- **Stage 100 : NO-GO jusqu’à un `PASS` réel du stage 30**
- **Extension fonctionnelle : NO-GO**

## Product Owner

### Retour

La progression pouvait auparavant être contournée en utilisant `continue_current_stage` avec une cible supérieure.

### Correction intégrée

Le backend exige maintenant les paramètres exacts de la campagne existante. Seul `start_next_stage` peut demander le successeur calculé par le serveur. Après 1 000 observations, aucun nouveau stage n’est proposé.

### Décision

La logique produit répond enfin à une seule question : « cette preuve autorise-t-elle exactement le prochain stage ? »

## Data Engineer

### Retour

Deux événements fournisseur pouvaient être associés au même résultat réel et gonfler l’échantillon. Les lignes hors plan pouvaient aussi déformer certaines couvertures.

### Correction intégrée

Le matching devient bijectif : le meilleur candidat déterministe est conservé et les autres associations sont classées `collision`. Les couvertures sont limitées aux cibles effectivement terminées. Le funnel expose les événements prêts par baseline.

### Décision

Les stages comptent des événements uniques et traçables, pas des lignes ou requêtes brutes.

## Quant / Statisticien

### Retour

Winamax plus un concurrent pouvait être présenté comme un consensus, alors que la baseline indépendante ne contenait qu’un bookmaker.

### Correction intégrée

Le consensus exige au moins deux bookmakers indépendants après exclusion de Winamax. Les compteurs `consensus` et `winamax` sont séparés et la décision utilise la baseline réellement sélectionnée.

### Décision

Le stage 30 reste une validation de pipeline. Il ne permet aucune conclusion robuste de supériorité ou de rentabilité.

## MLOps

### Retour

Plusieurs modules pouvaient afficher des verdicts différents pour une même campagne.

### Correction intégrée

Le rapport canonique produit `PASS`, `HOLD` ou `FAIL`. La porte de scale-up consomme ce contrat et distingue une preuve incomplète d’une corruption d’intégrité.

### Décision

Aucune promotion automatique n’est ajoutée. Un `PASS` rend seulement le stage suivant éligible à une approbation humaine.

## FinOps

### Retour

Une interruption pendant la découverte pouvait perdre l’état et conduire à repayer des appels. Le coût total mélangeait mal découverte et snapshots.

### Correction intégrée

Un checkpoint atomique est écrit après chaque appel facturable. Les appels au résultat de facturation incertain sont marqués et ne sont pas rejoués sans autorisation. Le rapport distingue `discovery_credits`, `snapshot_credits` et `total_credits`.

### Décision

Le plafond devient vérifiable sur la campagne complète. Un fournisseur ne garantissant pas un hard cap transactionnel impose toutefois une marge opérationnelle prudente.

## SRE

### Retour

La sonde `/api/health` pouvait déclarer l’application saine sans vérifier ses dépendances, et plusieurs workflows pouvaient modifier la production simultanément.

### Correction intégrée

Railway, Docker et la vérification post-déploiement utilisent `/api/ready`. Les workflows de déploiement, rollback, rebuild, campagne et recomputation partagent le groupe `production-change`.

### Décision

Le déploiement est acceptable après protection de l’environnement GitHub et vérification du commit réellement servi.

## QA

### Retour

Les défauts critiques n’étaient pas tous couverts par des tests de non-régression.

### Correction intégrée

La suite comporte maintenant 155 tests. Les scénarios V4.1 couvrent les contournements de stage, collisions, faux consensus, baseline, coûts, reprise partielle et classification `HOLD/FAIL`.

### Décision

La couverture cœur reste à 83 %. Les scripts d’opérations fournisseur restent une zone à renforcer, mais les chemins critiques V4.1 sont directement testés.

## Sécurité

### Retour

Les modifications de production doivent être sérialisées et la provenance des checkpoints doit être stricte.

### Correction intégrée

La restauration vérifie version, clé de campagne, stage, baseline, plafond, période et commit lorsque les deux commits sont connus. Le workflow possède explicitement `actions: read` pour récupérer les artefacts. Le verrou de production et l’environnement GitHub `production` réduisent les courses et permettent une approbation humaine.

### Risques résiduels

- actions GitHub non figées par SHA ;
- environnement `production` à protéger dans GitHub ;
- authentification et proxy à réévaluer avant une architecture multi-instance.

## Jeu responsable

### Retour

Le durcissement statistique ne doit pas devenir une automatisation de pari.

### Garanties conservées

- aucune connexion de compte bookmaker ;
- aucun pari automatique ;
- aucune recommandation de mise ;
- aucune promotion automatique ;
- aucune promesse de gain.

## Arbitrage final

Les rôles produit et exploitation souhaiteraient accélérer vers le stage 100. Les rôles data, quant, FinOps et sécurité refusent sans preuve réelle V4.1. L’arbitrage retenu est : déployer et vérifier la V4.1, exécuter d’abord un dry-run puis un stage 30 contrôlé, et maintenir le stage 100 bloqué jusqu’à un rapport canonique `PASS` identique dans l’artefact, l’API et Railway.
