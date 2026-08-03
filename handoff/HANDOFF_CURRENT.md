# HANDOFF CURRENT — Sports Prediction Lab

Generated: `2026-08-03T17:46:31.174572+00:00`

## Verified repository state

- App version: **4.2.0**
- Git branch: `unverified`
- Git commit: `unverified`
- Release ID: `aa06acb2dc86b77997ac`
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
├── shadow-cron         champion + market baselines + blend → results → settlement
└── Postgres            audit records, model/release registry, metrics and decisions

GitHub Actions
├── deploy-production.yml       tests → Railway deploy → API proof → Chromium smoke
├── verify-production.yml       read-only production proof
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
- Tennis remains experimental and uncalibrated.
- A green workflow is insufficient without /api/release post-deployment verification.
- The authenticated Chromium smoke test requires APP_PASSWORD as a GitHub Actions secret.
- Managed PostgreSQL backup restoration must be verified through the cloud backup workflow.
- Use Estimate evidence coverage before approving any paid evidence campaign.
- Only an exact VIABLE preflight may authorize a paid campaign.
- Stage 100 remains blocked until a real V4.2 stage-30 report returns PASS.
- A consensus requires at least two independent bookmakers after Winamax exclusion.
- No model promotion is automatic, even when all evidence gates pass.

## Files to attach in a new conversation

1. `START_HERE_NEXT_CHAT.md`
2. `handoff/HANDOFF_CURRENT.md`
3. `handoff/HANDOFF_CURRENT.json`
4. `artifacts/release_manifest.json`
5. The latest Railway or GitHub Actions log when troubleshooting

No secret, environment variable, database URL, cookie, API key or deployment token is exported.
