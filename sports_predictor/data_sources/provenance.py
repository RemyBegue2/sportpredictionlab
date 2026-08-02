from __future__ import annotations
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
import hashlib, json


def sha256_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


@dataclass
class DataManifest:
    sport: str
    source_name: str
    source_url: str
    retrieved_at_utc: str
    local_path: str
    sha256: str
    rows: int
    schema_version: str = "2.1"
    license_note: str = "Verify source terms before commercial use."

    @classmethod
    def from_file(cls, *, sport: str, source_name: str, source_url: str,
                  local_path: str | Path, rows: int, license_note: str = "") -> "DataManifest":
        p = Path(local_path)
        return cls(
            sport=sport,
            source_name=source_name,
            source_url=source_url,
            retrieved_at_utc=datetime.now(timezone.utc).isoformat(),
            local_path=str(p),
            sha256=sha256_file(p),
            rows=int(rows),
            license_note=license_note or cls.__dataclass_fields__["license_note"].default,
        )

    def write(self, path: str | Path) -> None:
        p = Path(path); p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(asdict(self), indent=2, ensure_ascii=False), encoding="utf-8")
