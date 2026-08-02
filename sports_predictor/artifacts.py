from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
import hashlib
import json


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_artifact_manifest(paths: Iterable[str | Path], destination: str | Path) -> dict:
    files = []
    for raw_path in paths:
        path = Path(raw_path)
        files.append({
            "name": path.name,
            "sha256": sha256_file(path),
            "bytes": path.stat().st_size,
        })
    payload = {
        "schema_version": "2.1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "files": files,
        "trust_note": "Integrity check only. Load artifacts only from a trusted distribution channel.",
    }
    target = Path(destination)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return payload


def verify_artifact_manifest(directory: str | Path, manifest_path: str | Path) -> dict:
    directory = Path(directory)
    manifest_path = Path(manifest_path)
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    for item in payload.get("files", []):
        name = item.get("name")
        expected = item.get("sha256")
        if not name or not expected:
            raise RuntimeError("Malformed artifact manifest")
        path = directory / name
        if not path.is_file():
            raise RuntimeError(f"Missing artifact declared in manifest: {name}")
        actual = sha256_file(path)
        if actual != expected:
            raise RuntimeError(f"Artifact integrity check failed: {name}")
    return payload
