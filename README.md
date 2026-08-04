# Sports Prediction Lab V4.9 — Controlled Model Decision & Live Validation

Application privée de recherche football et tennis. La vue simple conserve exactement trois écrans : **Aujourd’hui**, **Signaux** et **Apprentissage**. Les métriques avancées, datasets, holdouts et artefacts restent dans le mode expert.

## Ce que fait la V4.9

```text
Matchs du jour → probabilités → signal shadow ou abstention
→ données réglées → challengers bornés → décision hold/revue
→ nouveau holdout futur → promotion humaine uniquement
```

- entraîne exactement deux challengers football : Poisson régularisé et hybride Poisson/Elo ;
- sélectionne les hyperparamètres avant une validation de développement chronologique ;
- interdit de réutiliser le holdout déjà consulté comme preuve de promotion ;
- ouvre une génération de holdout future nécessitant 30 nouvelles dates ;
- ajoute un import tennis incrémental qui conserve les anciennes versions ;
- distingue ajouts, doublons inchangés et corrections de résultat ;
- exige deux preuves publiques longue session séparées : simple et expert ;
- consomme zéro crédit fournisseur pour l’import, l’entraînement et la validation navigateur.

## État réel livré

```text
Football : 1 900 matchs
Développement : 1 028 train · 250 calibration · 229 validation
Holdout déjà consulté : 393 matchs, diagnostic uniquement
Poisson régularisé : hold — veto nul et repos déséquilibré
Hybride Poisson/Elo : hold — ECE dégradée et mêmes vetos
Nouveau holdout de promotion : collecte future, 30 dates requises
Tennis : 32 matchs / 2 dates — 500 / 50 requis pour exploration
Production longue session : non prouvée tant que les deux workflows publics ne passent pas
```

## Interface

- **Aujourd’hui** — matchs et probabilités, huit cartes maximum ;
- **Signaux** — signaux expérimentaux ou abstentions ;
- **Apprentissage** — football, tennis, production et coût ;
- **Mode expert** — challengers, datasets, holdouts et diagnostics complets.

## Endpoints V4.9

```text
/api/controlled-model-decision
/api/controlled-model-decision/run
/api/evidence-acceleration
/api/challenger-factory
/api/feature-lab
/api/daily/slate
/api/research-lab
/api/release
/api/ready
```

## Workflows V4.9

```text
Run controlled model decision
Verify public long session — scénario simple
Verify public long session — scénario expert
Run evidence acceleration
Run sport challenger factory
Deploy production
Verify production
```

## Garde-fous

- aucun pari réel ou personnalisé ;
- aucune connexion bookmaker ;
- aucune martingale ;
- aucun entraînement direct sur le ROI passé ;
- aucune promotion automatique ;
- aucun challenger sous les seuils tennis ;
- aucune affirmation de rentabilité future.
