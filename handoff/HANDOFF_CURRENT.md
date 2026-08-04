# HANDOFF CURRENT — Sports Prediction Lab

Generated: `2026-08-04T12:52:13.844260+00:00`

## Verified repository state

- App version: **4.9.0**
- Git branch: `unknown`
- Git commit: `unknown`
- Release ID: `ed9b992f86509a811572`
- Running/source commit detected locally: `unverified`
- Artifact integrity: **OK**
- Football model version: `3.4.0-fresh`
- Football model SHA-256: `04ee949b38f8eebe1f937b15b4e560e7b3f0ddcb06babd3190ea7053fd3e82c4`
- Dataset SHA-256: `ae48ba7dc4715936f8891177f054c5a4799c681c0b65fc4bd7aea8031478eac7`
- Dataset cutoff: `2026-05-24T00:00:00+00:00`
- Model promoted by rebuild: `True`

## Architecture

```text
Railway
├── sportpredictionlab  FastAPI + private web UI
├── daily-product-cron  free fixtures → model-only probabilities → PostgreSQL
└── Postgres            audit records, model/release registry, metrics and decisions

GitHub Actions
├── deploy-production.yml       tests → Railway deploy → API proof → Chromium smoke
├── verify-production.yml       read-only production proof
├── refresh-daily-product.yml   zero-credit fixture/model refresh
├── automated-shadow-learning.yml bounded capture → settlement → challenger training
├── promote-research-champion.yml manual reviewed champion promotion
├── rebuild-fresh-football.yml  rebuild → tests → deploy → proof
├── estimate-historical-sample.yml  immutable zero-credit request plan
├── estimate-evidence-coverage.yml coverage probe → VIABLE/RISKY/NOT_VIABLE
├── run-evidence-campaign.yml       preflight-gated campaign → quality gate → Railway dashboard
├── recompute-latest-evidence.yml   latest GitHub artifact → zero-credit recalculation
├── backup-database.yml         backup → temporary restore verification
├── rollback-production.yml     restore from known Git commit → tests → deploy → proof
└── generate-handoff.yml        downloadable secret-free conversation bundle
```

## Non-negotiable rules

- Pre-match only.
- No Winamax account connection.
- No automatic bet placement.
- No staking recommendation.
- No silent rewriting of historical predictions.
- A blank shortlist is valid.
- Closing prices are evaluation evidence, not past features.

## Daily product

- Daily slate: `/api/daily/slate`
- Model diagnostics: `/api/model-diagnostics`
- Credit firewall: `/api/credit-firewall`
- Research learning state: `/api/research-lab/learning`
- Daily paid odds: **disabled by default**
- Historical paid evidence: **disabled by default**
- Automatic bet placement: **disabled**

## Evidence engine

- Champion–challenger artifact: `artifacts/champion_challenger_v3_6.json`
- Historical quality artifact: `artifacts/evidence_report_v3_9.json`
- Campaign artifact: `artifacts/evidence_campaign_v4.json`
- Coverage preflight: `artifacts/coverage_preflight_v4_2.json`
- Candidate campaign plan: `artifacts/candidate_campaign_plan_v4_2.json`
- Cloud control endpoint: `/api/control-center`
- Local Python required for operations: **no**
- Authenticated deterministic verdict: `/api/model-decision`
- Controlled stages: 30, 100, 300 and 1,000 event snapshots
- Automatic model promotion: **disabled**

## Open gates

- No profitability claim before a sufficiently large temporally valid sample.
- Tennis remains experimental; a base-model abstention requires at least 30 settled tennis events before meta-model rehabilitation.
- A green workflow is insufficient without /api/release post-deployment verification.
- The authenticated Chromium smoke test requires APP_PASSWORD as a GitHub Actions secret.
- Managed PostgreSQL backup restoration must be verified through the cloud backup workflow.
- Daily model-only predictions must consume zero provider credits.
- Daily odds and paid historical evidence remain disabled by default.
- Do not restart paid evidence without explicit human approval and a new justification.
- Stage 100 remains blocked until a real stage-30 report returns PASS.
- A consensus requires at least two independent bookmakers after Winamax exclusion.
- No model promotion is automatic, even when all evidence gates pass.

## Files to attach in a new conversation

1. `START_HERE_NEXT_CHAT.md`
2. `handoff/HANDOFF_CURRENT.md`
3. `handoff/HANDOFF_CURRENT.json`
4. `artifacts/release_manifest.json`
5. The latest Railway or GitHub Actions log when troubleshooting

No secret, environment variable, database URL, cookie, API key or deployment token is exported.
