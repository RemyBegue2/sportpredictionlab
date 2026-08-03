from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
import hashlib
import json
import os
import shutil
import subprocess

from .artifacts import sha256_file, verify_artifact_manifest

APP_VERSION = "3.8.0"
RELEASE_SCHEMA_VERSION = "1.0"
SENSITIVE_MARKERS = (
    "password",
    "secret",
    "token",
    "api_key",
    "database_url",
    "authorization",
    "cookie",
)


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _git_commit(root: Path) -> str:
    for name in ("SOURCE_COMMIT", "RAILWAY_GIT_COMMIT_SHA", "GITHUB_SHA"):
        value = (os.getenv(name) or "").strip()
        if value:
            return value
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
            timeout=3,
        )
        value = result.stdout.strip()
        return value or "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def _hash_optional(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    return {"path": str(path), "sha256": sha256_file(path), "bytes": path.stat().st_size}


def _sanitize(value: Any) -> Any:
    """Return a JSON-safe structure with secret-like fields removed."""
    if isinstance(value, dict):
        clean: dict[str, Any] = {}
        safe_flags = {"secrets_exported", "automatic_bet_placement", "staking_recommendations"}
        for raw_key, raw_value in value.items():
            key = str(raw_key)
            if key in safe_flags:
                clean[key] = _sanitize(raw_value)
            elif any(marker in key.casefold() for marker in SENSITIVE_MARKERS):
                clean[key] = "[redacted]"
            else:
                clean[key] = _sanitize(raw_value)
        return clean
    if isinstance(value, (list, tuple)):
        return [_sanitize(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    if hasattr(value, "item"):
        try:
            return value.item()
        except (TypeError, ValueError):
            pass
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def build_release_evidence(root: str | Path, *, version: str = APP_VERSION) -> dict[str, Any]:
    root_path = Path(root).resolve()
    artifact_dir = root_path / "artifacts"
    artifact_manifest = _read_json(artifact_dir / "artifact_manifest.json") or {}
    fresh_report = _read_json(artifact_dir / "fresh_rebuild_report.json") or {}
    metrics = _read_json(artifact_dir / "metrics.json") or {}

    declared = {
        str(item.get("name")): str(item.get("sha256"))
        for item in artifact_manifest.get("files", [])
        if isinstance(item, dict) and item.get("name") and item.get("sha256")
    }
    artifact_names = sorted(set(declared) | {
        "football_model.joblib",
        "tennis_model.joblib",
        "metrics.json",
    })
    artifacts: dict[str, Any] = {}
    integrity_ok = True
    for name in artifact_names:
        path = artifact_dir / name
        item = _hash_optional(path)
        if item is None:
            artifacts[name] = {"present": False, "declared_sha256": declared.get(name), "matches_manifest": False}
            if name in declared:
                integrity_ok = False
            continue
        actual = item["sha256"]
        expected = declared.get(name)
        matches = expected is None or expected == actual
        artifacts[name] = {
            "present": True,
            "sha256": actual,
            "bytes": item["bytes"],
            "declared_sha256": expected,
            "matches_manifest": matches,
        }
        integrity_ok = integrity_ok and matches

    code_files = {}
    for relative in (
        "webapp.py",
        "static/index.html",
        "static/app.js",
        "sports_predictor/release_registry.py",
        "sports_predictor/control_center.py",
        "sports_predictor/database.py",
        "sports_predictor/fresh_rebuild.py",
        ".github/workflows/rebuild-fresh-football.yml",
        ".github/workflows/deploy-production.yml",
        ".github/workflows/verify-production.yml",
        ".github/workflows/generate-handoff.yml",
        ".github/workflows/estimate-historical-sample.yml",
        ".github/workflows/run-historical-sample.yml",
        "sports_predictor/evidence_quality.py",
        "sports_predictor/sample_plan.py",
        "Dockerfile",
        "railway.toml",
        "railway.cron.toml",
    ):
        path = root_path / relative
        if path.is_file():
            code_files[relative] = {"sha256": sha256_file(path), "bytes": path.stat().st_size}

    source_commit = _git_commit(root_path)
    if source_commit == "unknown":
        packaged_manifest = _read_json(artifact_dir / "release_manifest.json") or {}
        packaged_commit = str(((packaged_manifest.get("app") or {}).get("source_commit") or "")).strip()
        if packaged_commit and packaged_commit != "unknown":
            source_commit = packaged_commit
    football_hash = (artifacts.get("football_model.joblib") or {}).get("sha256")
    dataset = fresh_report.get("dataset") if isinstance(fresh_report.get("dataset"), dict) else {}
    model_report = fresh_report.get("model") if isinstance(fresh_report.get("model"), dict) else {}
    model_version = (
        str(fresh_report.get("version")) + "-fresh"
        if fresh_report.get("promoted")
        else "snapshot"
    )
    release_material = "|".join([
        str(version),
        source_commit,
        str(football_hash or "missing"),
        str(dataset.get("sha256") or "unknown"),
    ])
    release_id = hashlib.sha256(release_material.encode("utf-8")).hexdigest()[:20]

    payload = {
        "schema_version": RELEASE_SCHEMA_VERSION,
        "release_id": release_id,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "app": {
            "name": "sports-prediction-lab",
            "version": str(version),
            "environment": os.getenv("APP_ENV", "development"),
            "source_commit": source_commit,
            "source_commit_short": source_commit[:12] if source_commit != "unknown" else "unknown",
            "deployment_id": os.getenv("RAILWAY_DEPLOYMENT_ID") or os.getenv("RENDER_INSTANCE_ID") or None,
            "service_id": os.getenv("RAILWAY_SERVICE_ID") or None,
        },
        "integrity": {
            "artifact_manifest_present": bool(artifact_manifest),
            "artifact_integrity_ok": integrity_ok,
            "artifacts": artifacts,
            "code_files": code_files,
        },
        "football_model": {
            "model_version": model_version,
            "artifact_sha256": football_hash,
            "promoted": bool(fresh_report.get("promoted")),
            "trained_until": model_report.get("trained_until") or dataset.get("last_date") or fresh_report.get("trained_until"),
            "dataset_sha256": dataset.get("sha256"),
            "dataset_rows": dataset.get("rows"),
            "dataset_cutoff": dataset.get("cutoff") or dataset.get("max_date") or dataset.get("last_date"),
            "promotion": fresh_report.get("promotion"),
        },
        "metrics_digest": {
            "football": metrics.get("football") if isinstance(metrics, dict) else None,
            "fresh_rebuild": fresh_report.get("evaluation") if isinstance(fresh_report, dict) else None,
        },
        "safety": {
            "secrets_exported": False,
            "automatic_bet_placement": False,
            "staking_recommendations": False,
        },
    }
    return _sanitize(payload)


def write_release_manifest(root: str | Path, destination: str | Path | None = None, *, version: str = APP_VERSION) -> dict[str, Any]:
    root_path = Path(root).resolve()
    target = Path(destination) if destination else root_path / "artifacts" / "release_manifest.json"
    payload = build_release_evidence(root_path, version=version)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return payload


def verify_release_manifest(root: str | Path, manifest_path: str | Path | None = None) -> dict[str, Any]:
    root_path = Path(root).resolve()
    path = Path(manifest_path) if manifest_path else root_path / "artifacts" / "release_manifest.json"
    payload = _read_json(path)
    if not payload:
        raise RuntimeError("Release manifest is missing or malformed")
    artifacts = ((payload.get("integrity") or {}).get("artifacts") or {})
    for name, item in artifacts.items():
        if not isinstance(item, dict) or not item.get("present"):
            continue
        artifact_path = root_path / "artifacts" / name
        if not artifact_path.is_file():
            raise RuntimeError(f"Release artifact missing: {name}")
        expected = item.get("sha256")
        if expected and sha256_file(artifact_path) != expected:
            raise RuntimeError(f"Release artifact hash mismatch: {name}")
    return payload


def snapshot_model_release(
    root: str | Path,
    *,
    release_id: str | None = None,
    files: Iterable[str] = ("football_model.joblib", "tennis_model.joblib", "metrics.json", "artifact_manifest.json", "fresh_rebuild_report.json"),
) -> dict[str, Any]:
    root_path = Path(root).resolve()
    evidence = build_release_evidence(root_path)
    snapshot_id = release_id or str(evidence["release_id"])
    if not snapshot_id or any(char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_." for char in snapshot_id):
        raise ValueError("Invalid release_id")
    target = root_path / "artifacts" / "releases" / snapshot_id
    target.mkdir(parents=True, exist_ok=False)
    copied: list[str] = []
    for name in files:
        source = root_path / "artifacts" / name
        if source.is_file():
            shutil.copy2(source, target / name)
            copied.append(name)
    active_data = root_path / "data" / "real" / "football_active.csv"
    if active_data.is_file():
        shutil.copy2(active_data, target / "football_active.csv")
        copied.append("football_active.csv")
    snapshot_manifest = {
        "schema_version": "1.0",
        "release_id": snapshot_id,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "files": [
            {"name": name, "sha256": sha256_file(target / name), "bytes": (target / name).stat().st_size}
            for name in copied
        ],
        "release_evidence": evidence,
    }
    (target / "snapshot_manifest.json").write_text(
        json.dumps(snapshot_manifest, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return snapshot_manifest


def rollback_model_release(root: str | Path, *, release_id: str, dry_run: bool = True) -> dict[str, Any]:
    root_path = Path(root).resolve()
    if not release_id or any(char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_." for char in release_id):
        raise ValueError("Invalid release_id")
    source_dir = root_path / "artifacts" / "releases" / release_id
    manifest = _read_json(source_dir / "snapshot_manifest.json")
    if not manifest:
        raise RuntimeError("Snapshot manifest is missing")
    planned: list[dict[str, str]] = []
    for item in manifest.get("files", []):
        name = str(item.get("name") or "")
        expected = str(item.get("sha256") or "")
        source = source_dir / name
        if not source.is_file() or not expected or sha256_file(source) != expected:
            raise RuntimeError(f"Invalid snapshot file: {name}")
        destination = root_path / "data" / "real" / name if name == "football_active.csv" else root_path / "artifacts" / name
        planned.append({"source": str(source), "destination": str(destination)})
    if dry_run:
        return {"status": "dry_run", "release_id": release_id, "planned": planned}

    backup = snapshot_model_release(root_path, release_id=f"before-rollback-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}")
    for item in planned:
        source = Path(item["source"])
        destination = Path(item["destination"])
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(destination.suffix + ".rollback.tmp")
        shutil.copy2(source, temporary)
        os.replace(temporary, destination)
    artifact_manifest_path = root_path / "artifacts" / "artifact_manifest.json"
    if artifact_manifest_path.is_file():
        verify_artifact_manifest(root_path / "artifacts", artifact_manifest_path)
    write_release_manifest(root_path, version=APP_VERSION)
    return {
        "status": "rolled_back",
        "release_id": release_id,
        "backup_release_id": backup["release_id"],
        "restored": planned,
    }
