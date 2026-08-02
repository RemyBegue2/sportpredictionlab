from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
from typing import Any

from sports_predictor.release_registry import APP_VERSION, build_release_evidence

ROOT = Path(__file__).resolve().parents[1]


def git_value(*args: str) -> str:
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
    integration_status = read_json("artifacts/integration_status_v3_5.json")
    security_scan = read_json("artifacts/security_scan_v3_5.json")
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
        "deployment": {
            "platform": "Railway",
            "services": ["sportpredictionlab", "shadow-cron", "Postgres"],
            "public_url": "not_exported",
            "verification_endpoint": "/api/release",
        },
        "next_priority": "Accumulate and evaluate shadow observations by model and horizon; do not claim market outperformance without evidence.",
        "known_gates": [
            "No profitability claim before a sufficiently large temporally valid sample.",
            "Tennis remains experimental and uncalibrated.",
            "A green workflow is insufficient without /api/release post-deployment verification.",
            "Managed PostgreSQL backup restoration remains to be verified on the real Railway project.",
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
├── shadow-cron         odds → frozen predictions → results → settlement
└── Postgres            audit records, model/release registry, metrics

GitHub Actions
└── rebuild-fresh-football.yml
    ├── rebuild candidate
    ├── tests
    ├── release manifest + handoff export
    ├── commit generated evidence
    ├── Railway deploy when credentials exist
    └── post-deploy proof when APP_PUBLIC_URL is configured
```

## Non-negotiable rules

- Pre-match only.
- No Winamax account connection.
- No automatic bet placement.
- No staking recommendation.
- No silent rewriting of historical predictions.
- A blank shortlist is valid.
- Closing prices are evaluation evidence, not past features.

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
    print(json.dumps({
        "status": "ok",
        "json": str(json_path.relative_to(ROOT)),
        "markdown": str(md_path.relative_to(ROOT)),
        "secrets_exported": False,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
