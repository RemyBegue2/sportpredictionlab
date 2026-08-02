from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import zipfile

from scripts.export_handoff import main as export_handoff_main

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FILES = (
    "START_HERE_NEXT_CHAT.md",
    "NEXT_CHAT_PROMPT.txt",
    "README.md",
    "UPGRADE_V3_7.md",
    "AUDIT_MULTI_ROLES_V3_7.md",
    "RESULTATS_V3_7.md",
    "DECISION_LOG.md",
    "KNOWN_ISSUES_AND_GATES.md",
    "OPERATIONS_RUNBOOK.md",
    "handoff/HANDOFF_CURRENT.md",
    "handoff/HANDOFF_CURRENT.json",
    "handoff/LAST_BENCHMARK_SUMMARY.json",
    "handoff/ACTIVE_MODEL_CARD.md",
    "handoff/NEXT_ACTIONS.md",
    "artifacts/release_manifest.json",
    "artifacts/integration_status_v3_7.json",
    "artifacts/security_scan_v3_7.json",
)


def build_bundle(destination: Path) -> dict[str, object]:
    # export_handoff parses argv, so generate files directly through a subprocess-safe import alternative
    from scripts.export_handoff import build_handoff, markdown, active_model_card, next_actions

    handoff_dir = ROOT / "handoff"
    handoff_dir.mkdir(parents=True, exist_ok=True)
    payload = build_handoff()
    (handoff_dir / "HANDOFF_CURRENT.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8"
    )
    (handoff_dir / "HANDOFF_CURRENT.md").write_text(markdown(payload), encoding="utf-8")
    (handoff_dir / "LAST_BENCHMARK_SUMMARY.json").write_text(
        json.dumps(payload.get("champion_challenger") or {"status": "not_run"}, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (handoff_dir / "ACTIVE_MODEL_CARD.md").write_text(active_model_card(payload), encoding="utf-8")
    (handoff_dir / "NEXT_ACTIONS.md").write_text(next_actions(payload), encoding="utf-8")

    included: list[str] = []
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for relative in DEFAULT_FILES:
            path = ROOT / relative
            if path.is_file():
                archive.write(path, arcname=relative)
                included.append(relative)
        manifest = {
            "schema_version": "1.0",
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "files": included,
            "secrets_exported": False,
            "local_python_required": False,
            "usage": "Attach this ZIP to a new ChatGPT conversation and use NEXT_CHAT_PROMPT.txt.",
        }
        archive.writestr("BUNDLE_MANIFEST.json", json.dumps(manifest, ensure_ascii=False, indent=2))
    return {"status": "ok", "output": str(destination), "files": included, "secrets_exported": False}


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a secret-free handoff ZIP for GitHub Actions artifacts.")
    parser.add_argument("--output", default="dist/sports-prediction-handoff-v3.7.zip")
    args = parser.parse_args()
    result = build_bundle(ROOT / args.output)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
