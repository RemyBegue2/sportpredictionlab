from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path


def _truthy(value: str | None, *, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().casefold() in {"1", "true", "yes", "on"}


def _csv(value: str | None, default: tuple[str, ...]) -> tuple[str, ...]:
    if not value:
        return default
    return tuple(item.strip() for item in value.split(",") if item.strip())


@dataclass(frozen=True)
class CloudSettings:
    environment: str
    auth_required: bool
    app_password: str | None
    session_secret: str
    cookie_secure: bool
    database_url: str
    odds_sync_sports: tuple[str, ...]
    odds_stale_minutes: int
    model_version: str
    shadow_enabled: bool = True
    shadow_max_events: int = 50
    shadow_quota_floor: int = 100
    model_max_age_days: int = 365

    @classmethod
    def from_env(cls, root: Path | None = None) -> "CloudSettings":
        base = root or Path.cwd()
        environment = os.getenv("APP_ENV", "development").strip().lower()
        cloud_detected = bool(os.getenv("RAILWAY_ENVIRONMENT") or os.getenv("RENDER"))
        auth_required = _truthy(os.getenv("APP_AUTH_REQUIRED"), default=cloud_detected)
        session_secret = os.getenv("APP_SESSION_SECRET", "")
        if not session_secret and not auth_required:
            # Development-only deterministic fallback. Production readiness rejects it.
            session_secret = "development-only-change-me"
        raw_db = os.getenv("DATABASE_URL") or f"sqlite:///{Path(os.getenv('APP_DATABASE_PATH', '/tmp/sports_prediction_v3_5.db'))}"
        if raw_db.startswith("postgres://"):
            raw_db = "postgresql+psycopg://" + raw_db.removeprefix("postgres://")
        elif raw_db.startswith("postgresql://") and "+" not in raw_db.split(":", 1)[0]:
            raw_db = "postgresql+psycopg://" + raw_db.removeprefix("postgresql://")
        stale_raw = os.getenv("ODDS_STALE_MINUTES", "15")
        try:
            stale = max(1, min(1440, int(stale_raw)))
        except ValueError:
            stale = 15
        try:
            shadow_max_events = max(1, min(500, int(os.getenv("SHADOW_MAX_EVENTS", "50"))))
        except ValueError:
            shadow_max_events = 50
        try:
            shadow_quota_floor = max(0, int(os.getenv("SHADOW_QUOTA_FLOOR", "100")))
        except ValueError:
            shadow_quota_floor = 100
        try:
            model_max_age_days = max(30, min(3650, int(os.getenv("MODEL_MAX_AGE_DAYS", "365"))))
        except ValueError:
            model_max_age_days = 365
        return cls(
            environment=environment,
            auth_required=auth_required,
            app_password=os.getenv("APP_PASSWORD") or None,
            session_secret=session_secret,
            cookie_secure=_truthy(os.getenv("APP_COOKIE_SECURE"), default=environment == "production" or cloud_detected),
            database_url=raw_db,
            odds_sync_sports=_csv(os.getenv("ODDS_SYNC_SPORTS"), ("soccer_epl",)),
            odds_stale_minutes=stale,
            model_version=os.getenv("MODEL_VERSION", "3.8.0"),
            shadow_enabled=_truthy(os.getenv("SHADOW_MODE_ENABLED"), default=True),
            shadow_max_events=shadow_max_events,
            shadow_quota_floor=shadow_quota_floor,
            model_max_age_days=model_max_age_days,
        )

    @property
    def production_ready(self) -> bool:
        return not self.readiness_issues()

    def readiness_issues(self) -> list[str]:
        issues: list[str] = []
        if self.auth_required and not self.app_password:
            issues.append("APP_PASSWORD is missing")
        if self.auth_required and len(self.app_password or "") < 12:
            issues.append("APP_PASSWORD must contain at least 12 characters")
        if self.auth_required and len(self.session_secret) < 32:
            issues.append("APP_SESSION_SECRET must contain at least 32 characters")
        if self.environment == "production" and self.database_url.startswith("sqlite"):
            issues.append("Production must use PostgreSQL through DATABASE_URL")
        if self.environment == "production" and not self.cookie_secure:
            issues.append("APP_COOKIE_SECURE must be enabled in production")
        return issues
