# Sports Prediction Lab — point de reprise V4.0

## État canonique

- Base stable avant upgrade : V3.9.2.
- Version préparée : V4.0.0 Controlled Evidence Scale-Up.
- Exploitation : GitHub Actions + Railway uniquement ; aucun Python local.
- Nouveau workflow : `.github/workflows/run-evidence-campaign.yml`.
- Stages : 30, 100, 300, 1 000.
- Baseline par défaut : consensus.
- Aucune promotion automatique, aucune mise, aucun pari automatique.

## Première action après déploiement

```text
Actions → Run evidence campaign → dry_run → stage 30 → 350 crédits → consensus
```

Le dry-run doit être vert avant toute exécution payante.

## Fichiers prioritaires à joindre dans une nouvelle conversation

- `START_HERE_NEXT_CHAT.md`
- `handoff/HANDOFF_CURRENT.md`
- `handoff/HANDOFF_CURRENT.json`
- dernier `evidence_campaign_v4.json`
- log exact du workflow en cas d’échec
