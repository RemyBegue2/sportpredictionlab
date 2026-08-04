from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
from typing import Any

from sports_predictor.release_registry import APP_VERSION, build_release_evidence

ROOT = Path(__file__).resolve().parents[1]


def git_value(*args: str) -> str:
    if args == ("branch", "--show-current"):
        override = (os.getenv("SOURCE_BRANCH") or os.getenv("GITHUB_REF_NAME") or "").strip()
        if override:
            return override
    if args == ("rev-parse", "HEAD"):
        override = (os.getenv("SOURCE_COMMIT") or os.getenv("GITHUB_SHA") or "").strip()
        if override:
            return override
    if args == ("rev-parse", "--short", "HEAD"):
        override = (os.getenv("SOURCE_COMMIT") or os.getenv("GITHUB_SHA") or "").strip()
        if override:
            return override[:12]
    try:
        result = subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True, text=True, timeout=3)
        return result.stdout.strip() or "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def read_json(relative: str) -> dict[str, Any] | None:
    path = ROOT / relative
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def build_handoff() -> dict[str, Any]:
    evidence = build_release_evidence(ROOT, version=APP_VERSION)
    report = read_json("artifacts/fresh_rebuild_report.json")
    artifact_manifest = read_json("artifacts/artifact_manifest.json")
    release_manifest = read_json("artifacts/release_manifest.json")
    validation = read_json("VALIDATION_V4_9.json")
    integration_status = ({
        "status": "ready_for_controlled_deploy",
        "version": APP_VERSION,
        "validation": validation,
        "required_user_actions": [
            "Deploy production version 4.9.0",
            "Verify the stable cockpit, session status and sport challenger states in Chromium",
            "Keep paid capture disabled until a small shadow experiment is explicitly approved",
        ],
    } if validation else None)
    security_scan = read_json("artifacts/security_scan_v3_9.json") or read_json("artifacts/security_scan_v3_8.json") or read_json("artifacts/security_scan_v3_7.json") or read_json("artifacts/security_scan_v3_6.json") or read_json("artifacts/security_scan_v3_5.json")
    evidence_bundle = read_json("artifacts/champion_challenger_v3_6.json")
    evidence_report = read_json("artifacts/evidence_report_v3_9.json") or read_json("artifacts/evidence_report_v3_8.json")
    evidence_campaign = read_json("artifacts/evidence_campaign_v4.json")
    evidence_campaign_plan = read_json("artifacts/evidence_campaign_plan_v4.json")
    coverage_preflight = read_json("artifacts/coverage_preflight_v4_2.json")
    candidate_campaign_plan = read_json("artifacts/candidate_campaign_plan_v4_2.json")
    challenger_factory = read_json("artifacts/challenger_factory_v4_9.json")
    return {
        "schema_version": "1.0",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "project": "Sports Prediction Lab",
        "current_version": APP_VERSION,
        "git": {
            "branch": git_value("branch", "--show-current"),
            "commit": git_value("rev-parse", "HEAD"),
            "commit_short": git_value("rev-parse", "--short", "HEAD"),
        },
        "release": evidence,
        "fresh_rebuild_report": report,
        "artifact_manifest": artifact_manifest,
        "release_manifest": release_manifest,
        "integration_status": integration_status,
        "security_scan": security_scan,
        "champion_challenger": evidence_bundle,
        "historical_evidence": evidence_report,
        "evidence_campaign": evidence_campaign,
        "evidence_campaign_plan": evidence_campaign_plan,
        "coverage_preflight": coverage_preflight,
        "candidate_campaign_plan": candidate_campaign_plan,
        "challenger_factory": challenger_factory,
        "evidence_acceleration": read_json("artifacts/evidence_acceleration_v4_9.json"),
        "controlled_model_decision": read_json("artifacts/controlled_model_decision_v4_9.json"),
        "model_decision": (evidence_bundle or {}).get("decision") if evidence_bundle else None,
        "deployment": {
            "platform": "Railway",
            "services": ["sportpredictionlab", "daily-product-cron", "Postgres"],
            "cloud_jobs": [
                "GitHub Actions daily product refresh",
                "bounded automated shadow capture and settlement",
                "weekly zero-credit calibration and sport challenger training",
            ],
            "public_url": "not_exported",
            "verification_endpoint": "/api/release",
        },
        "next_priority": "Deploy V4.9, run the controlled model decision at zero credits, and execute both public long-session scenarios before any model promotion review.",
        "known_gates": [
            "No profitability claim before a sufficiently large temporally valid sample.",
            "Tennis remains experimental; a base-model abstention requires at least 30 settled tennis events before meta-model rehabilitation.",
            "A green workflow is insufficient without /api/release post-deployment verification.",
            "The authenticated Chromium smoke test requires APP_PASSWORD as a GitHub Actions secret.",
            "Managed PostgreSQL backup restoration must be verified through the cloud backup workflow.",
            "Daily model-only predictions must consume zero provider credits.",
            "Daily odds and paid historical evidence remain disabled by default.",
            "Do not restart paid evidence without explicit human approval and a new justification.",
            "Stage 100 remains blocked until a real stage-30 report returns PASS.",
            "A consensus requires at least two independent bookmakers after Winamax exclusion.",
            "No model promotion is automatic, even when all evidence gates pass.",
        ],
        "safety": {
            "secrets_exported": False,
            "automatic_bet_placement": False,
            "staking_recommendations": False,
        },
    }


def markdown(payload: dict[str, Any]) -> str:
    release = payload["release"]
    app = release.get("app") or {}
    model = release.get("football_model") or {}
    integrity = release.get("integrity") or {}
    git = payload.get("git") or {}
    gates = "\n".join(f"- {item}" for item in payload.get("known_gates", []))
    return f"""# HANDOFF CURRENT — Sports Prediction Lab

Generated: `{payload['generated_at_utc']}`

## Verified repository state

- App version: **{payload['current_version']}**
- Git branch: `{git.get('branch')}`
- Git commit: `{git.get('commit')}`
- Release ID: `{release.get('release_id')}`
- Running/source commit detected locally: `{app.get('source_commit')}`
- Artifact integrity: **{'OK' if integrity.get('artifact_integrity_ok') else 'NOT VERIFIED'}**
- Football model version: `{model.get('model_version')}`
- Football model SHA-256: `{model.get('artifact_sha256')}`
- Dataset SHA-256: `{model.get('dataset_sha256')}`
- Dataset cutoff: `{model.get('dataset_cutoff')}`
- Model promoted by rebuild: `{model.get('promoted')}`

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

{gates}

## Files to attach in a new conversation

1. `START_HERE_NEXT_CHAT.md`
2. `handoff/HANDOFF_CURRENT.md`
3. `handoff/HANDOFF_CURRENT.json`
4. `artifacts/release_manifest.json`
5. The latest Railway or GitHub Actions log when troubleshooting

No secret, environment variable, database URL, cookie, API key or deployment token is exported.
"""


def active_model_card(payload: dict[str, Any]) -> str:
    model = ((payload.get("release") or {}).get("football_model") or {})
    decision = payload.get("model_decision") or {}
    return f"""# ACTIVE MODEL CARD

- App version: `{payload.get('current_version')}`
- Model version: `{model.get('model_version')}`
- Model SHA-256: `{model.get('artifact_sha256')}`
- Dataset SHA-256: `{model.get('dataset_sha256')}`
- Dataset cutoff: `{model.get('dataset_cutoff')}`
- Evidence status: `{decision.get('status', 'not_evaluable')}`
- Evidence reason: {decision.get('reason', 'No champion–challenger report has been generated.')}
- Automatic promotion: **disabled**
- Automatic bet placement: **disabled**
"""


def next_actions(payload: dict[str, Any]) -> str:
    decision = payload.get("model_decision") or {}
    action = "Deploy V4.9, verify the three-tab cockpit and /api/controlled-model-decision, then run both public long-session scenarios before any promotion review."
    return f"""# NEXT ACTIONS

1. {action}
2. Confirm `/api/credit-firewall` keeps daily odds and historical evidence disabled by default.
3. Follow `OPERATIONS_RUNBOOK_V4_9.md` to run the controlled model decision and incremental tennis import.
4. Use GitHub Actions → Generate handoff package, then attach the downloaded ZIP in the next conversation.

No secret is exported.
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Export a secret-free project handoff for another conversation.")
    parser.add_argument("--directory", default="handoff")
    args = parser.parse_args()
    target = ROOT / args.directory
    target.mkdir(parents=True, exist_ok=True)
    payload = build_handoff()
    json_path = target / "HANDOFF_CURRENT.json"
    md_path = target / "HANDOFF_CURRENT.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    md_path.write_text(markdown(payload), encoding="utf-8")
    benchmark_path = target / "LAST_BENCHMARK_SUMMARY.json"
    benchmark_path.write_text(json.dumps(payload.get("champion_challenger") or {"status": "not_run"}, ensure_ascii=False, indent=2), encoding="utf-8")
    model_card_path = target / "ACTIVE_MODEL_CARD.md"
    model_card_path.write_text(active_model_card(payload), encoding="utf-8")
    actions_path = target / "NEXT_ACTIONS.md"
    actions_path.write_text(next_actions(payload), encoding="utf-8")
    print(json.dumps({
        "status": "ok",
        "json": str(json_path.relative_to(ROOT)),
        "markdown": str(md_path.relative_to(ROOT)),
        "benchmark": str(benchmark_path.relative_to(ROOT)),
        "model_card": str(model_card_path.relative_to(ROOT)),
        "next_actions": str(actions_path.relative_to(ROOT)),
        "secrets_exported": False,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
