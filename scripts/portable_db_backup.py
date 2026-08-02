from __future__ import annotations

import argparse
from dataclasses import replace
from datetime import date, datetime, timezone
import gzip
import json
from pathlib import Path
from typing import Any

from sqlalchemy import MetaData, create_engine, delete, func, insert, select, text

from sports_predictor.cloud_config import CloudSettings
from sports_predictor.database import Base

ROOT = Path(__file__).resolve().parents[1]
TABLE_ORDER = [table.name for table in Base.metadata.sorted_tables]


def json_value(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return {"__type__": "datetime", "value": value.isoformat()}
    if isinstance(value, bytes):
        return {"__type__": "bytes", "value": value.hex()}
    if isinstance(value, dict):
        return {str(key): json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_value(item) for item in value]
    return value


def from_json_value(value: Any) -> Any:
    if isinstance(value, dict) and value.get("__type__") == "datetime":
        return datetime.fromisoformat(str(value["value"]).replace("Z", "+00:00"))
    if isinstance(value, dict) and value.get("__type__") == "bytes":
        return bytes.fromhex(str(value["value"]))
    if isinstance(value, dict):
        return {key: from_json_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [from_json_value(item) for item in value]
    return value


def engine_for(url: str):
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    return create_engine(url, future=True, pool_pre_ping=True, connect_args=connect_args)


def backup(database_url: str, output: Path) -> dict[str, Any]:
    engine = engine_for(database_url)
    metadata = MetaData()
    metadata.reflect(bind=engine)
    tables: dict[str, Any] = {}
    with engine.connect() as connection:
        for name in TABLE_ORDER:
            table = metadata.tables.get(name)
            if table is None:
                continue
            rows = [json_value(dict(row._mapping)) for row in connection.execute(select(table))]
            tables[name] = {"row_count": len(rows), "rows": rows}
    payload = {
        "schema_version": "1.0",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "table_order": TABLE_ORDER,
        "tables": tables,
        "secrets_exported": False,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(output, "wt", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, sort_keys=True)
    return {"status": "ok", "output": str(output), "tables": {name: data["row_count"] for name, data in tables.items()}}


def restore(target_url: str, backup_path: Path, *, execute: bool, allow_nonempty: bool = False) -> dict[str, Any]:
    with gzip.open(backup_path, "rt", encoding="utf-8") as handle:
        payload = json.load(handle)
    if payload.get("schema_version") != "1.0":
        raise RuntimeError("Unsupported backup schema")

    settings = replace(CloudSettings.from_env(ROOT), database_url=target_url)
    target_engine = engine_for(settings.database_url)
    Base.metadata.create_all(target_engine)
    metadata = MetaData()
    metadata.reflect(bind=target_engine)

    existing: dict[str, int] = {}
    with target_engine.connect() as connection:
        for name in payload.get("table_order", []):
            table = metadata.tables.get(name)
            if table is not None:
                existing[name] = int(connection.scalar(select(func.count()).select_from(table)) or 0)
    if any(existing.values()) and not allow_nonempty:
        raise RuntimeError("Restore target is not empty; use a new database or pass --allow-nonempty explicitly")

    plan = {
        name: int((payload.get("tables", {}).get(name) or {}).get("row_count", 0))
        for name in payload.get("table_order", [])
    }
    if not execute:
        return {"status": "dry_run", "target_tables": existing, "restore_plan": plan}

    with target_engine.begin() as connection:
        if allow_nonempty:
            for name in reversed(payload.get("table_order", [])):
                table = metadata.tables.get(name)
                if table is not None:
                    connection.execute(delete(table))
        for name in payload.get("table_order", []):
            table = metadata.tables.get(name)
            table_payload = payload.get("tables", {}).get(name) or {}
            rows = [from_json_value(row) for row in table_payload.get("rows", [])]
            if table is not None and rows:
                connection.execute(insert(table), rows)
        if target_engine.dialect.name == "postgresql":
            for name in payload.get("table_order", []):
                table = metadata.tables.get(name)
                if table is None or len(table.primary_key.columns) != 1:
                    continue
                pk = next(iter(table.primary_key.columns))
                if not getattr(pk.type, "python_type", None) is int:
                    continue
                sequence = connection.scalar(
                    text("SELECT pg_get_serial_sequence(:table_name, :column_name)"),
                    {"table_name": name, "column_name": pk.name},
                )
                if not sequence:
                    continue
                maximum = connection.scalar(select(func.max(pk)))
                if maximum is None:
                    connection.execute(text("SELECT setval(:sequence, 1, false)"), {"sequence": sequence})
                else:
                    connection.execute(text("SELECT setval(:sequence, :value, true)"), {"sequence": sequence, "value": int(maximum)})
    return {"status": "restored", "restored": plan}


def main() -> None:
    parser = argparse.ArgumentParser(description="Create or verify a portable application-level database backup.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--backup", action="store_true")
    mode.add_argument("--restore", action="store_true")
    parser.add_argument("--file")
    parser.add_argument("--database-url")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--allow-nonempty", action="store_true")
    args = parser.parse_args()

    settings = CloudSettings.from_env(ROOT)
    if args.backup:
        output = Path(args.file) if args.file else ROOT / "backups" / f"portable-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json.gz"
        result = backup(args.database_url or settings.database_url, output)
    else:
        if not args.file:
            parser.error("--file is required for restore")
        if not args.database_url:
            parser.error("--database-url must point to a separate restore target")
        result = restore(args.database_url, Path(args.file), execute=args.execute, allow_nonempty=args.allow_nonempty)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
