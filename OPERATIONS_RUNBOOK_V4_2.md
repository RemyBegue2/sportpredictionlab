# Operations Runbook V4.2

## 1. Déployer

Lancer `Deploy production`, puis vérifier :

- `/api/health` répond ;
- `/api/ready` renvoie `ready` ;
- `/api/release` affiche la version `4.2.0`, le commit attendu et le hash de modèle attendu ;
- `/api/coverage-preflight` répond, même lorsqu'aucun préflight n'a encore été publié.

## 2. Exécuter un préflight

Workflow : `Estimate evidence coverage`.

Paramètres initiaux recommandés pour le stage 30 :

```text
baseline: consensus
target_stage: 30
max_preflight_credits: 120
max_campaign_credits: 650
max_discovery_calls: 14
max_probe_events: 12
confirmation: EXECUTE_PREFLIGHT
retry_uncertain_preflight: false
```

Le préflight consomme réellement des crédits. Le plafond inclut la découverte et les sondes.

## 3. Interpréter le verdict

### VIABLE

Le rapport contient un plan candidat hashé. Une campagne peut être proposée, mais reste soumise à approbation humaine.

### RISKY

La couverture observée est prometteuse mais l'incertitude reste trop forte. Utiliser uniquement la fenêtre de suivi proposée et lancer un nouveau préflight plafonné. Ne pas lancer la campagne complète.

### NOT_VIABLE

Ne pas lancer de backfill. Lire la cause : couverture manifestement insuffisante, budget trop faible, absence d'événements ou pool candidat insuffisant.

## 4. Exécuter une campagne

Workflow : `Run evidence campaign`.

Le workflow vérifie que le préflight :

- est `VIABLE` ;
- correspond à la baseline, au stage, au budget et à la version ;
- appartient au type d'expérience principal ;
- contient un plan candidat et une liste d'événements intègres ;
- recommande au moins autant d'événements que le stage demandé.

Le planificateur matérialise ensuite exactement le plan candidat intégré au rapport. Toute altération bloque l'exécution.

## 5. Reprise

Une reprise exige :

- le même `preflight_id` ;
- le même `candidate_plan_id` ;
- les mêmes dates, baseline, stage et plafond ;
- un préflight toujours valide et intègre.

Un appel marqué `uncertain` ne doit pas être rejoué avant vérification du tableau fournisseur et activation explicite de l'option de retry.

## 6. Arrêts obligatoires

Arrêter et ne pas augmenter l'échelle si :

- le préflight n'est pas `VIABLE` ;
- le stage 30 n'est pas `PASS` ;
- une fuite temporelle, un doublon ou une collision apparaît ;
- le budget réel dépasse le plafond ;
- les verdicts GitHub, artefact, API et Railway divergent.
