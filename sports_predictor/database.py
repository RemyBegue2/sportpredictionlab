from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Iterator, Mapping

import pandas as pd
from sqlalchemy import DateTime, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint, create_engine, func, select, text
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker

from .cloud_config import CloudSettings


class Base(DeclarativeBase):
    pass


class EventRecord(Base):
    __tablename__ = "events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider_event_id: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    sport_key: Mapped[str] = mapped_column(String(100), index=True)
    commence_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    home_name: Mapped[str] = mapped_column(String(180))
    away_name: Mapped[str] = mapped_column(String(180))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    snapshots: Mapped[list["OddsSnapshotRecord"]] = relationship(back_populates="event", cascade="all, delete-orphan")


class OddsSnapshotRecord(Base):
    __tablename__ = "odds_snapshots"
    __table_args__ = (
        UniqueConstraint("event_id", "bookmaker_key", "market_key", "outcome_name", "observed_at", "price", name="uq_odds_snapshot"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), index=True)
    bookmaker_key: Mapped[str] = mapped_column(String(80), index=True)
    bookmaker_title: Mapped[str | None] = mapped_column(String(160))
    market_key: Mapped[str] = mapped_column(String(80), index=True)
    outcome_name: Mapped[str] = mapped_column(String(180))
    price: Mapped[float] = mapped_column(Float)
    point: Mapped[float | None] = mapped_column(Float)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    event: Mapped[EventRecord] = relationship(back_populates="snapshots")


class PredictionRecord(Base):
    __tablename__ = "predictions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider_event_id: Mapped[str | None] = mapped_column(String(160), index=True)
    sport: Mapped[str] = mapped_column(String(40), index=True)
    model_version: Mapped[str] = mapped_column(String(40), index=True)
    fixture: Mapped[dict[str, Any]] = mapped_column(JSON)
    probabilities: Mapped[dict[str, Any]] = mapped_column(JSON)
    market_analysis: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    decision: Mapped[str] = mapped_column(String(80), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)


class SyncRunRecord(Base):
    __tablename__ = "sync_runs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_name: Mapped[str] = mapped_column(String(120), index=True)
    sport_key: Mapped[str | None] = mapped_column(String(100), index=True)
    status: Mapped[str] = mapped_column(String(40), index=True)
    fetched_events: Mapped[int] = mapped_column(Integer, default=0)
    inserted_snapshots: Mapped[int] = mapped_column(Integer, default=0)
    quota_remaining: Mapped[int | None] = mapped_column(Integer)
    quota_last_cost: Mapped[int | None] = mapped_column(Integer)
    error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)
    finished_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class EventResultRecord(Base):
    __tablename__ = "event_results"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), unique=True, index=True)
    home_score: Mapped[int] = mapped_column(Integer)
    away_score: Mapped[int] = mapped_column(Integer)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    source: Mapped[str] = mapped_column(String(120))
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class BenchmarkRunRecord(Base):
    __tablename__ = "benchmark_runs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sport_key: Mapped[str] = mapped_column(String(100), index=True)
    model_version: Mapped[str] = mapped_column(String(40), index=True)
    status: Mapped[str] = mapped_column(String(40), index=True)
    config: Mapped[dict[str, Any]] = mapped_column(JSON)
    summary: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    report: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DataQualityIssueRecord(Base):
    __tablename__ = "data_quality_issues"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    issue_type: Mapped[str] = mapped_column(String(100), index=True)
    severity: Mapped[str] = mapped_column(String(30), index=True)
    provider_event_id: Mapped[str | None] = mapped_column(String(160), index=True)
    details: Mapped[dict[str, Any]] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(30), default="open", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)


class BackfillJobRecord(Base):
    __tablename__ = "backfill_jobs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sport_key: Mapped[str] = mapped_column(String(100), index=True)
    status: Mapped[str] = mapped_column(String(40), index=True)
    plan: Mapped[dict[str, Any]] = mapped_column(JSON)
    request_count: Mapped[int] = mapped_column(Integer, default=0)
    completed_requests: Mapped[int] = mapped_column(Integer, default=0)
    estimated_credits: Mapped[int] = mapped_column(Integer, default=0)
    consumed_credits: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


_ENGINE = None
_SESSION_FACTORY: sessionmaker[Session] | None = None
_SETTINGS: CloudSettings | None = None


def _utc(value: Any, fallback: datetime | None = None) -> datetime:
    parsed = pd.to_datetime(value, utc=True, errors="coerce")
    if pd.isna(parsed):
        return fallback or datetime.now(timezone.utc)
    return parsed.to_pydatetime()


def _first_present(*values: Any) -> Any:
    for value in values:
        if value is None:
            continue
        try:
            if pd.isna(value):
                continue
        except (TypeError, ValueError):
            pass
        return value
    return None


def _json_safe(value: Any) -> Any:
    return json.loads(json.dumps(value, default=lambda obj: obj.item() if hasattr(obj, "item") else str(obj)))


def configure_database(settings: CloudSettings, *, force: bool = False) -> None:
    global _ENGINE, _SESSION_FACTORY, _SETTINGS
    if _ENGINE is not None and not force and _SETTINGS == settings:
        return
    connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
    _ENGINE = create_engine(settings.database_url, pool_pre_ping=True, future=True, connect_args=connect_args)
    _SESSION_FACTORY = sessionmaker(bind=_ENGINE, expire_on_commit=False, future=True)
    _SETTINGS = settings


def init_database(settings: CloudSettings) -> None:
    configure_database(settings)
    assert _ENGINE is not None
    Base.metadata.create_all(_ENGINE)


def dispose_database() -> None:
    global _ENGINE, _SESSION_FACTORY, _SETTINGS
    if _ENGINE is not None:
        _ENGINE.dispose()
    _ENGINE = None
    _SESSION_FACTORY = None
    _SETTINGS = None


@contextmanager
def session_scope() -> Iterator[Session]:
    if _SESSION_FACTORY is None:
        raise RuntimeError("Database is not configured")
    session = _SESSION_FACTORY()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def ping_database() -> bool:
    if _ENGINE is None:
        return False
    try:
        with _ENGINE.connect() as connection:
            connection.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


def persist_odds_rows(rows: pd.DataFrame, *, fetched_at: Any, quota_remaining: int | None = None, quota_last_cost: int | None = None, job_name: str = "live_slate", sport_key: str | None = None) -> dict[str, int]:
    started = datetime.now(timezone.utc)
    inserted = 0
    events_seen: set[str] = set()
    fetched_dt = _utc(fetched_at)
    if rows.empty:
        record_sync_run(job_name=job_name, sport_key=sport_key, status="ok", fetched_events=0, inserted_snapshots=0, quota_remaining=quota_remaining, quota_last_cost=quota_last_cost, started_at=started)
        return {"events": 0, "inserted_snapshots": 0}
    try:
        with session_scope() as session:
            for item in rows.to_dict(orient="records"):
                event_key = str(item.get("event_id") or "").strip()
                bookmaker = str(item.get("bookmaker_key") or "").strip()
                market = str(item.get("market_key") or "").strip()
                outcome = str(item.get("outcome_name") or "").strip()
                price = item.get("price")
                if not event_key or not bookmaker or not market or not outcome or pd.isna(price):
                    continue
                events_seen.add(event_key)
                event = session.scalar(select(EventRecord).where(EventRecord.provider_event_id == event_key))
                if event is None:
                    event = EventRecord(
                        provider_event_id=event_key,
                        sport_key=str(item.get("sport_key") or sport_key or "unknown"),
                        commence_time=_utc(item.get("commence_time")) if item.get("commence_time") is not None else None,
                        home_name=str(item.get("home_team") or ""),
                        away_name=str(item.get("away_team") or ""),
                    )
                    session.add(event)
                    session.flush()
                else:
                    event.updated_at = datetime.now(timezone.utc)
                    event.commence_time = _utc(item.get("commence_time"), event.commence_time) if item.get("commence_time") is not None else event.commence_time
                    event.home_name = str(item.get("home_team") or event.home_name)
                    event.away_name = str(item.get("away_team") or event.away_name)
                observed = _utc(_first_present(item.get("market_last_update"), item.get("bookmaker_last_update"), item.get("snapshot_time")), fetched_dt)
                point = item.get("point")
                point_value = None if point is None or pd.isna(point) else float(point)
                exists = session.scalar(select(OddsSnapshotRecord.id).where(
                    OddsSnapshotRecord.event_id == event.id,
                    OddsSnapshotRecord.bookmaker_key == bookmaker,
                    OddsSnapshotRecord.market_key == market,
                    OddsSnapshotRecord.outcome_name == outcome,
                    OddsSnapshotRecord.observed_at == observed,
                    OddsSnapshotRecord.price == float(price),
                ))
                if exists is None:
                    session.add(OddsSnapshotRecord(
                        event_id=event.id,
                        bookmaker_key=bookmaker,
                        bookmaker_title=str(item.get("bookmaker_title") or "") or None,
                        market_key=market,
                        outcome_name=outcome,
                        price=float(price),
                        point=point_value,
                        observed_at=observed,
                        fetched_at=fetched_dt,
                    ))
                    inserted += 1
        record_sync_run(job_name=job_name, sport_key=sport_key, status="ok", fetched_events=len(events_seen), inserted_snapshots=inserted, quota_remaining=quota_remaining, quota_last_cost=quota_last_cost, started_at=started)
        return {"events": len(events_seen), "inserted_snapshots": inserted}
    except Exception as exc:
        record_sync_run(job_name=job_name, sport_key=sport_key, status="error", fetched_events=len(events_seen), inserted_snapshots=inserted, quota_remaining=quota_remaining, quota_last_cost=quota_last_cost, error_message=str(exc)[:1000], started_at=started)
        raise


def record_sync_run(*, job_name: str, sport_key: str | None, status: str, fetched_events: int, inserted_snapshots: int, quota_remaining: int | None, quota_last_cost: int | None, error_message: str | None = None, started_at: datetime | None = None) -> None:
    with session_scope() as session:
        session.add(SyncRunRecord(
            job_name=job_name,
            sport_key=sport_key,
            status=status,
            fetched_events=fetched_events,
            inserted_snapshots=inserted_snapshots,
            quota_remaining=quota_remaining,
            quota_last_cost=quota_last_cost,
            error_message=error_message,
            started_at=started_at or datetime.now(timezone.utc),
            finished_at=datetime.now(timezone.utc),
        ))


def record_prediction(*, sport: str, model_version: str, fixture: Mapping[str, Any], probabilities: Mapping[str, Any], market_analysis: Mapping[str, Any] | None, decision: str, provider_event_id: str | None = None) -> int:
    with session_scope() as session:
        record = PredictionRecord(
            provider_event_id=provider_event_id,
            sport=sport,
            model_version=model_version,
            fixture=_json_safe(dict(fixture)),
            probabilities=_json_safe(dict(probabilities)),
            market_analysis=_json_safe(dict(market_analysis)) if market_analysis else None,
            decision=decision,
        )
        session.add(record)
        session.flush()
        return int(record.id)


def recent_predictions(limit: int = 50) -> list[dict[str, Any]]:
    with session_scope() as session:
        records = session.scalars(select(PredictionRecord).order_by(PredictionRecord.created_at.desc()).limit(max(1, min(200, limit)))).all()
        return [{
            "id": row.id,
            "provider_event_id": row.provider_event_id,
            "sport": row.sport,
            "model_version": row.model_version,
            "fixture": row.fixture,
            "probabilities": row.probabilities,
            "market_analysis": row.market_analysis,
            "decision": row.decision,
            "created_at": row.created_at.isoformat(),
        } for row in records]


def predictions_for_date(date_value: str, *, limit: int = 1000) -> list[dict[str, Any]]:
    rows = recent_predictions(limit)
    matching = [row for row in rows if str((row.get("fixture") or {}).get("date", "")) == date_value]
    deduplicated: dict[str, dict[str, Any]] = {}
    for row in matching:
        fixture = row.get("fixture") or {}
        key = str(row.get("provider_event_id") or json.dumps(fixture, sort_keys=True, ensure_ascii=False))
        if key not in deduplicated:
            deduplicated[key] = row
    return list(deduplicated.values())


def recent_sync_runs(limit: int = 20) -> list[dict[str, Any]]:
    with session_scope() as session:
        rows = session.scalars(select(SyncRunRecord).order_by(SyncRunRecord.started_at.desc()).limit(max(1, min(100, limit)))).all()
        return [{
            "id": row.id,
            "job_name": row.job_name,
            "sport_key": row.sport_key,
            "status": row.status,
            "fetched_events": row.fetched_events,
            "inserted_snapshots": row.inserted_snapshots,
            "quota_remaining": row.quota_remaining,
            "quota_last_cost": row.quota_last_cost,
            "error_message": row.error_message,
            "started_at": row.started_at.isoformat(),
            "finished_at": row.finished_at.isoformat(),
        } for row in rows]



def persist_event_result(*, provider_event_id: str, home_score: int, away_score: int, completed_at: Any, source: str = "the_odds_api_scores") -> int:
    if home_score < 0 or away_score < 0:
        raise ValueError("scores must be non-negative")
    with session_scope() as session:
        event = session.scalar(select(EventRecord).where(EventRecord.provider_event_id == provider_event_id))
        if event is None:
            raise ValueError(f"unknown provider event id: {provider_event_id}")
        record = session.scalar(select(EventResultRecord).where(EventResultRecord.event_id == event.id))
        if record is None:
            record = EventResultRecord(
                event_id=event.id,
                home_score=int(home_score),
                away_score=int(away_score),
                completed_at=_utc(completed_at),
                source=str(source),
            )
            session.add(record)
        else:
            record.home_score = int(home_score)
            record.away_score = int(away_score)
            record.completed_at = _utc(completed_at)
            record.source = str(source)
        session.flush()
        return int(record.id)


def record_data_quality_issue(*, issue_type: str, severity: str, details: Mapping[str, Any], provider_event_id: str | None = None) -> int:
    if severity not in {"info", "warning", "error", "critical"}:
        raise ValueError("invalid severity")
    with session_scope() as session:
        record = DataQualityIssueRecord(
            issue_type=str(issue_type),
            severity=severity,
            provider_event_id=provider_event_id,
            details=_json_safe(dict(details)),
        )
        session.add(record)
        session.flush()
        return int(record.id)


def recent_data_quality_issues(limit: int = 100) -> list[dict[str, Any]]:
    with session_scope() as session:
        rows = session.scalars(select(DataQualityIssueRecord).order_by(DataQualityIssueRecord.created_at.desc()).limit(max(1, min(500, limit)))).all()
        return [{
            "id": row.id,
            "issue_type": row.issue_type,
            "severity": row.severity,
            "provider_event_id": row.provider_event_id,
            "details": row.details,
            "status": row.status,
            "created_at": row.created_at.isoformat(),
        } for row in rows]


def create_backfill_job(*, sport_key: str, plan: Mapping[str, Any], request_count: int, estimated_credits: int) -> int:
    with session_scope() as session:
        record = BackfillJobRecord(
            sport_key=sport_key,
            status="planned",
            plan=_json_safe(dict(plan)),
            request_count=int(request_count),
            estimated_credits=int(estimated_credits),
        )
        session.add(record)
        session.flush()
        return int(record.id)


def update_backfill_job(job_id: int, *, status: str | None = None, completed_requests: int | None = None, consumed_credits: int | None = None, error_message: str | None = None) -> None:
    with session_scope() as session:
        record = session.get(BackfillJobRecord, int(job_id))
        if record is None:
            raise ValueError("unknown backfill job")
        if status is not None:
            record.status = status
        if completed_requests is not None:
            record.completed_requests = int(completed_requests)
        if consumed_credits is not None:
            record.consumed_credits = int(consumed_credits)
        record.error_message = error_message
        record.updated_at = datetime.now(timezone.utc)


def recent_backfill_jobs(limit: int = 20) -> list[dict[str, Any]]:
    with session_scope() as session:
        rows = session.scalars(select(BackfillJobRecord).order_by(BackfillJobRecord.created_at.desc()).limit(max(1, min(100, limit)))).all()
        return [{
            "id": row.id,
            "sport_key": row.sport_key,
            "status": row.status,
            "request_count": row.request_count,
            "completed_requests": row.completed_requests,
            "estimated_credits": row.estimated_credits,
            "consumed_credits": row.consumed_credits,
            "error_message": row.error_message,
            "created_at": row.created_at.isoformat(),
            "updated_at": row.updated_at.isoformat(),
        } for row in rows]


def record_benchmark_run(*, sport_key: str, model_version: str, status: str, config: Mapping[str, Any], report: Mapping[str, Any] | None = None, summary: Mapping[str, Any] | None = None, error_message: str | None = None) -> int:
    now = datetime.now(timezone.utc)
    with session_scope() as session:
        record = BenchmarkRunRecord(
            sport_key=sport_key,
            model_version=model_version,
            status=status,
            config=_json_safe(dict(config)),
            report=_json_safe(dict(report)) if report else None,
            summary=_json_safe(dict(summary)) if summary else None,
            error_message=error_message,
            started_at=now,
            finished_at=now if status in {"completed", "failed", "not_evaluable"} else None,
        )
        session.add(record)
        session.flush()
        return int(record.id)


def latest_benchmark_run(sport_key: str | None = None) -> dict[str, Any] | None:
    with session_scope() as session:
        statement = select(BenchmarkRunRecord).order_by(BenchmarkRunRecord.started_at.desc())
        if sport_key:
            statement = statement.where(BenchmarkRunRecord.sport_key == sport_key)
        row = session.scalar(statement.limit(1))
        if row is None:
            return None
        return {
            "id": row.id,
            "sport_key": row.sport_key,
            "model_version": row.model_version,
            "status": row.status,
            "config": row.config,
            "summary": row.summary,
            "report": row.report,
            "error_message": row.error_message,
            "started_at": row.started_at.isoformat(),
            "finished_at": row.finished_at.isoformat() if row.finished_at else None,
        }


def benchmark_source_rows(*, sport_key: str, bookmaker_key: str = "winamax_fr") -> list[dict[str, Any]]:
    """Return auditable event/result/snapshot rows for offline benchmark preparation.

    This deliberately does not construct model probabilities inside the database layer.
    """
    with session_scope() as session:
        statement = (
            select(EventRecord, EventResultRecord, OddsSnapshotRecord)
            .join(EventResultRecord, EventResultRecord.event_id == EventRecord.id)
            .join(OddsSnapshotRecord, OddsSnapshotRecord.event_id == EventRecord.id)
            .where(EventRecord.sport_key == sport_key, OddsSnapshotRecord.bookmaker_key == bookmaker_key)
            .order_by(EventRecord.commence_time, OddsSnapshotRecord.observed_at)
        )
        rows = session.execute(statement).all()
        return [{
            "event_id": event.provider_event_id,
            "sport_key": event.sport_key,
            "commence_time": event.commence_time.isoformat() if event.commence_time else None,
            "home_team": event.home_name,
            "away_team": event.away_name,
            "home_score": result.home_score,
            "away_score": result.away_score,
            "result_available_at": result.completed_at.isoformat(),
            "bookmaker_key": snapshot.bookmaker_key,
            "market_key": snapshot.market_key,
            "outcome_name": snapshot.outcome_name,
            "price": snapshot.price,
            "odds_observed_at": snapshot.observed_at.isoformat(),
        } for event, result, snapshot in rows]

def database_summary() -> dict[str, Any]:
    if not ping_database():
        return {"connected": False, "events": 0, "odds_snapshots": 0, "predictions": 0, "event_results": 0, "benchmark_runs": 0, "open_data_quality_issues": 0, "last_snapshot_at": None, "last_sync_at": None}
    with session_scope() as session:
        event_count = int(session.scalar(select(func.count(EventRecord.id))) or 0)
        snapshot_count = int(session.scalar(select(func.count(OddsSnapshotRecord.id))) or 0)
        prediction_count = int(session.scalar(select(func.count(PredictionRecord.id))) or 0)
        result_count = int(session.scalar(select(func.count(EventResultRecord.id))) or 0)
        benchmark_count = int(session.scalar(select(func.count(BenchmarkRunRecord.id))) or 0)
        open_quality_issues = int(session.scalar(select(func.count(DataQualityIssueRecord.id)).where(DataQualityIssueRecord.status == "open")) or 0)
        last_snapshot = session.scalar(select(func.max(OddsSnapshotRecord.observed_at)))
        last_sync = session.scalar(select(func.max(SyncRunRecord.finished_at)))
        return {
            "connected": True,
            "events": event_count,
            "odds_snapshots": snapshot_count,
            "predictions": prediction_count,
            "event_results": result_count,
            "benchmark_runs": benchmark_count,
            "open_data_quality_issues": open_quality_issues,
            "last_snapshot_at": last_snapshot.isoformat() if last_snapshot else None,
            "last_sync_at": last_sync.isoformat() if last_sync else None,
        }
