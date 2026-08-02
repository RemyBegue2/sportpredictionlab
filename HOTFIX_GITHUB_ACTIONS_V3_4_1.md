# Hotfix V3.4.1 — dates mixtes après fresh rebuild

## Symptôme

Le workflow télécharge et reconstruit correctement le dataset, puis plusieurs tests API échouent avec :

```text
time data "2026-08-02" doesn't match format "%Y-%m-%dT%H:%M:%S%z"
```

## Cause

Après la reconstruction, l'historique utilise des timestamps ISO complets tandis que les fixtures des endpoints utilisent parfois une date `YYYY-MM-DD`. Pandas 2.x infère un format unique pour toute la série et refuse le mélange.

## Correction

Les parseurs centraux de `sports_predictor/common.py` utilisent désormais :

```python
pd.to_datetime(..., utc=True, errors="raise", format="mixed")
```

La correction couvre le tri chronologique et la création des splits groupés.

## Validation

- 77 tests réussis.
- Les cinq tests auparavant en échec passent.
- Test de régression ajouté pour les dates simples et timestamps ISO mélangés.
