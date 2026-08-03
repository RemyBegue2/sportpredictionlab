from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import io
import json
import math
from pathlib import Path
from typing import Any, Iterable, Mapping
from urllib.parse import urlparse

import numpy as np
import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .identity import football_model_name, normalize_identity


FIXTURES_URL = "https://www.football-data.co.uk/fixtures.csv"
ESPN_SCOREBOARD_URL = "https://site.api.espn.com/apis/site/v2/sports/soccer/eng.1/scoreboard"
_ALLOWED_FIXTURE_HOST = "www.football-data.co.uk"
_ALLOWED_ESPN_HOST = "site.api.espn.com"
MAX_FIXTURE_DOWNLOAD_BYTES = 5 * 1024 * 1024


class DailyFixtureError(RuntimeError):
    """Raised when the zero-credit fixture feed cannot be used safely."""


def _bounded_response_bytes(response: Any) -> bytes:
    """Read an HTTP response without trusting an unbounded remote body."""
    raw_length = response.headers.get("Content-Length") if hasattr(response, "headers") else None
    try:
        if raw_length is not None and int(raw_length) > MAX_FIXTURE_DOWNLOAD_BYTES:
            raise DailyFixtureError("Fixture payload exceeds the download size limit")
    except (TypeError, ValueError):
        pass
    if hasattr(response, "iter_content"):
        chunks: list[bytes] = []
        consumed = 0
        for chunk in response.iter_content(chunk_size=64 * 1024):
            if not chunk:
                continue
            consumed += len(chunk)
            if consumed > MAX_FIXTURE_DOWNLOAD_BYTES:
                raise DailyFixtureError("Fixture payload exceeds the download size limit")
            chunks.append(bytes(chunk))
        return b"".join(chunks)
    payload = bytes(response.content)
    if len(payload) > MAX_FIXTURE_DOWNLOAD_BYTES:
        raise DailyFixtureError("Fixture payload exceeds the download size limit")
    return payload


@dataclass(frozen=True)
class FixtureSnapshot:
    fixtures: pd.DataFrame
    source: str
    fetched_at: str
    from_cache: bool
    sha256: str


class FootballFixtureSource:
    """Zero-credit upcoming fixture feed with an on-disk cache.

    The host is fixed for SSRF protection. The source is deliberately separate
    from The Odds API: obtaining a calendar must not consume betting-data
    credits or prevent model-only predictions from being displayed.
    """

    def __init__(
        self,
        cache_dir: str | Path = "data/daily_fixtures",
        *,
        url: str = FIXTURES_URL,
        timeout_seconds: float = 10.0,
        cache_ttl_seconds: int = 6 * 60 * 60,
        session: requests.Session | None = None,
    ) -> None:
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.hostname != _ALLOWED_FIXTURE_HOST:
            raise ValueError("Fixture source host is fixed for SSRF protection")
        self.url = url
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.raw_path = self.cache_dir / "football_data_fixtures.csv"
        self.meta_path = self.cache_dir / "football_data_fixtures.meta.json"
        self.timeout_seconds = float(timeout_seconds)
        self.cache_ttl_seconds = max(60, int(cache_ttl_seconds))
        self.session = session or requests.Session()
        retry = Retry(total=1, backoff_factor=0.5, status_forcelist=(429, 500, 502, 503, 504))
        self.session.mount("https://", HTTPAdapter(max_retries=retry))
        self.session.headers["User-Agent"] = "sports-prediction-lab/0.4.4.0"

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def _sha256(payload: bytes) -> str:
        return hashlib.sha256(payload).hexdigest()

    def _cache_is_fresh(self) -> bool:
        if not self.raw_path.exists() or not self.meta_path.exists():
            return False
        try:
            meta = json.loads(self.meta_path.read_text(encoding="utf-8"))
            fetched = datetime.fromisoformat(str(meta["fetched_at"]).replace("Z", "+00:00"))
        except (OSError, KeyError, ValueError, json.JSONDecodeError):
            return False
        return (self._now() - fetched.astimezone(timezone.utc)).total_seconds() <= self.cache_ttl_seconds

    def _read_cached(self) -> FixtureSnapshot:
        if not self.raw_path.exists():
            raise DailyFixtureError("No cached fixture feed is available")
        payload = self.raw_path.read_bytes()
        meta: dict[str, Any] = {}
        if self.meta_path.exists():
            try:
                meta = json.loads(self.meta_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                meta = {}
        return FixtureSnapshot(
            fixtures=self.normalize_csv(payload),
            source=self.url,
            fetched_at=str(meta.get("fetched_at") or datetime.fromtimestamp(self.raw_path.stat().st_mtime, timezone.utc).isoformat()),
            from_cache=True,
            sha256=self._sha256(payload),
        )

    def fetch(self, *, force: bool = False, allow_network: bool = True) -> FixtureSnapshot:
        if not force and self._cache_is_fresh():
            return self._read_cached()
        if not allow_network:
            return self._read_cached()
        try:
            response = self.session.get(
                self.url,
                timeout=self.timeout_seconds,
                headers={"Accept": "text/csv,*/*;q=0.8"},
                stream=True,
            )
            response.raise_for_status()
            payload = _bounded_response_bytes(response)
        except requests.RequestException as exc:
            if self.raw_path.exists():
                return self._read_cached()
            raise DailyFixtureError(f"Fixture feed request failed: {type(exc).__name__}") from exc
        fixtures = self.normalize_csv(payload)
        temporary = self.raw_path.with_suffix(".csv.tmp")
        temporary.write_bytes(payload)
        temporary.replace(self.raw_path)
        fetched_at = self._now().isoformat()
        meta = {"source": self.url, "fetched_at": fetched_at, "sha256": self._sha256(payload), "rows": len(fixtures)}
        meta_tmp = self.meta_path.with_suffix(".json.tmp")
        meta_tmp.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
        meta_tmp.replace(self.meta_path)
        return FixtureSnapshot(fixtures=fixtures, source=self.url, fetched_at=fetched_at, from_cache=False, sha256=meta["sha256"])

    @staticmethod
    def normalize_csv(payload: bytes) -> pd.DataFrame:
        try:
            source = pd.read_csv(io.BytesIO(payload), encoding="utf-8")
        except UnicodeDecodeError:
            source = pd.read_csv(io.BytesIO(payload), encoding="cp1252")
        aliases = {
            "league": ("Div", "League", "league"),
            "date": ("Date", "date"),
            "time": ("Time", "time", "Kickoff"),
            "home_team": ("HomeTeam", "Home", "home_team"),
            "away_team": ("AwayTeam", "Away", "away_team"),
        }

        def column(name: str, *, required: bool = True) -> str | None:
            match = next((candidate for candidate in aliases[name] if candidate in source.columns), None)
            if required and match is None:
                raise DailyFixtureError(f"Fixture feed schema missing {name}")
            return match

        league_col = column("league")
        date_col = column("date")
        home_col = column("home_team")
        away_col = column("away_team")
        time_col = column("time", required=False)
        date_text = source[date_col].astype("string").str.strip()
        if time_col:
            time_text = source[time_col].astype("string").fillna("").str.strip().replace("", "12:00")
            combined = (date_text + " " + time_text).str.strip()
        else:
            # Noon preserves the advertised local calendar date when converted
            # to UTC, unlike midnight during British Summer Time.
            combined = (date_text + " 12:00").str.strip()
        parsed = pd.to_datetime(combined, dayfirst=True, errors="coerce")
        # Football-Data fixture timestamps are presented as UK local time when
        # a time exists. Date-only rows remain valid calendar fixtures.
        if getattr(parsed.dt, "tz", None) is None:
            parsed = parsed.dt.tz_localize("Europe/London", ambiguous="NaT", nonexistent="shift_forward").dt.tz_convert("UTC")
        out = pd.DataFrame({
            "date": parsed,
            "league": source[league_col].astype("string").str.strip().str.upper(),
            "home_team": source[home_col].astype("string").str.strip(),
            "away_team": source[away_col].astype("string").str.strip(),
        })
        out = out.dropna(subset=["date", "league", "home_team", "away_team"])
        out = out[(out["home_team"] != "") & (out["away_team"] != "") & (out["home_team"] != out["away_team"])]
        out["fixture_date"] = out["date"].dt.date.astype(str)
        return (
            out.drop_duplicates(["date", "league", "home_team", "away_team"], keep="last")
            .sort_values(["date", "league", "home_team"], kind="stable")
            .reset_index(drop=True)
        )


class EspnFixtureSource:
    """Unauthenticated ESPN site scoreboard used only as a fixture calendar.

    The endpoint is unofficial and therefore never a single point of failure:
    responses are cached per day and the composite source below falls back to
    Football-Data. No odds, prices or betting recommendations are consumed.
    """

    def __init__(
        self,
        cache_dir: str | Path = "data/daily_fixtures/espn",
        *,
        url: str = ESPN_SCOREBOARD_URL,
        timeout_seconds: float = 8.0,
        cache_ttl_seconds: int = 6 * 60 * 60,
        session: requests.Session | None = None,
    ) -> None:
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.hostname != _ALLOWED_ESPN_HOST:
            raise ValueError("ESPN fixture source host is fixed for SSRF protection")
        self.url = url
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.timeout_seconds = float(timeout_seconds)
        self.cache_ttl_seconds = max(60, int(cache_ttl_seconds))
        self.session = session or requests.Session()
        retry = Retry(total=1, backoff_factor=0.5, status_forcelist=(429, 500, 502, 503, 504))
        self.session.mount("https://", HTTPAdapter(max_retries=retry))
        self.session.headers["User-Agent"] = "sports-prediction-lab/0.4.4.0"

    @staticmethod
    def _date_token(value: str | datetime | pd.Timestamp) -> str:
        parsed = pd.Timestamp(value)
        return parsed.strftime("%Y%m%d")

    def _cache_path(self, token: str) -> Path:
        return self.cache_dir / f"eng1_{token}.json"

    def _fresh(self, path: Path) -> bool:
        if not path.exists():
            return False
        modified = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
        return (datetime.now(timezone.utc) - modified).total_seconds() <= self.cache_ttl_seconds

    @staticmethod
    def normalize_payload(payload: Mapping[str, Any]) -> pd.DataFrame:
        rows: list[dict[str, Any]] = []
        for event in payload.get("events") or []:
            competitions = event.get("competitions") or []
            competition = competitions[0] if competitions else {}
            competitors = competition.get("competitors") or []
            home = next((item for item in competitors if item.get("homeAway") == "home"), None)
            away = next((item for item in competitors if item.get("homeAway") == "away"), None)
            if not home or not away:
                continue
            home_name = str((home.get("team") or {}).get("displayName") or "").strip()
            away_name = str((away.get("team") or {}).get("displayName") or "").strip()
            commence = pd.to_datetime(event.get("date") or competition.get("date"), utc=True, errors="coerce")
            if not home_name or not away_name or pd.isna(commence):
                continue
            rows.append({
                "date": commence,
                "league": "E0",
                "home_team": home_name,
                "away_team": away_name,
                "fixture_date": commence.date().isoformat(),
            })
        if not rows:
            return pd.DataFrame(columns=["date", "league", "home_team", "away_team", "fixture_date"])
        return (
            pd.DataFrame(rows)
            .drop_duplicates(["date", "league", "home_team", "away_team"], keep="last")
            .sort_values(["date", "home_team"], kind="stable")
            .reset_index(drop=True)
        )

    def fetch_window(
        self,
        *,
        requested_date: str,
        horizon_days: int,
        allow_network: bool = True,
    ) -> FixtureSnapshot:
        start = pd.Timestamp(requested_date)
        end = start + pd.Timedelta(days=max(0, int(horizon_days)))
        start_token = self._date_token(start)
        end_token = self._date_token(end)
        query_token = start_token if start_token == end_token else f"{start_token}-{end_token}"
        path = self._cache_path(query_token)
        payload: bytes | None = None
        from_cache = False
        if self._fresh(path) or not allow_network:
            if path.exists():
                payload = path.read_bytes()
                from_cache = True
        if payload is None and allow_network:
            try:
                response = self.session.get(
                    self.url, params={"dates": query_token, "limit": "1000"},
                    timeout=self.timeout_seconds, headers={"Accept": "application/json"}, stream=True,
                )
                response.raise_for_status()
                payload = _bounded_response_bytes(response)
                temporary = path.with_suffix(".json.tmp")
                temporary.write_bytes(payload)
                temporary.replace(path)
            except requests.RequestException as exc:
                if path.exists():
                    payload = path.read_bytes()
                    from_cache = True
                else:
                    raise DailyFixtureError("ESPN fixture feed unavailable and no cache exists") from exc
        if payload is None:
            raise DailyFixtureError("ESPN fixture feed unavailable and no cache exists")
        try:
            decoded = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise DailyFixtureError("ESPN fixture payload is not valid JSON") from exc
        fixtures = self.normalize_payload(decoded)
        fetched_at = (
            datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()
            if path.exists() else datetime.now(timezone.utc).isoformat()
        )
        return FixtureSnapshot(
            fixtures=fixtures, source=self.url, fetched_at=fetched_at,
            from_cache=from_cache, sha256=hashlib.sha256(payload).hexdigest(),
        )



class DailyFixtureSource:
    """Composite zero-credit calendar with cached provider fallback."""

    def __init__(
        self,
        cache_dir: str | Path = "data/daily_fixtures",
        *,
        cache_ttl_seconds: int = 6 * 60 * 60,
        failure_backoff_seconds: int = 15 * 60,
    ) -> None:
        root = Path(cache_dir)
        root.mkdir(parents=True, exist_ok=True)
        self.espn = EspnFixtureSource(root / "espn", cache_ttl_seconds=cache_ttl_seconds)
        self.football_data = FootballFixtureSource(root / "football_data", cache_ttl_seconds=cache_ttl_seconds)
        self.failure_path = root / "fixture_sources.failure.json"
        self.failure_backoff_seconds = max(60, min(int(failure_backoff_seconds), int(cache_ttl_seconds)))

    def _failure_is_recent(self) -> bool:
        if not self.failure_path.exists():
            return False
        try:
            payload = json.loads(self.failure_path.read_text(encoding="utf-8"))
            failed_at = datetime.fromisoformat(str(payload["failed_at"]).replace("Z", "+00:00"))
        except (OSError, KeyError, ValueError, json.JSONDecodeError):
            return False
        return (datetime.now(timezone.utc) - failed_at.astimezone(timezone.utc)).total_seconds() < self.failure_backoff_seconds

    def _record_failure(self, errors: Iterable[str]) -> None:
        payload = {
            "failed_at": datetime.now(timezone.utc).isoformat(),
            "errors": list(errors),
        }
        temporary = self.failure_path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        temporary.replace(self.failure_path)

    def _clear_failure(self) -> None:
        try:
            self.failure_path.unlink(missing_ok=True)
        except OSError:
            pass

    def fetch_window(self, *, requested_date: str, horizon_days: int, allow_network: bool = True) -> FixtureSnapshot:
        network_allowed_now = bool(allow_network and not self._failure_is_recent())
        espn_snapshot: FixtureSnapshot | None = None
        errors: list[str] = []
        try:
            espn_snapshot = self.espn.fetch_window(
                requested_date=requested_date, horizon_days=horizon_days, allow_network=network_allowed_now,
            )
            if not espn_snapshot.fixtures.empty:
                self._clear_failure()
                return espn_snapshot
        except DailyFixtureError as exc:
            errors.append(f"ESPN:{type(exc).__name__}")

        football_snapshot: FixtureSnapshot | None = None
        try:
            raw = self.football_data.fetch(force=False, allow_network=network_allowed_now)
            football_snapshot = FixtureSnapshot(
                fixtures=select_fixture_window(
                    raw.fixtures, requested_date=requested_date, horizon_days=horizon_days, leagues=("E0",),
                ),
                source=raw.source, fetched_at=raw.fetched_at, from_cache=raw.from_cache, sha256=raw.sha256,
            )
        except DailyFixtureError as exc:
            errors.append(f"FootballData:{type(exc).__name__}")

        available = [item for item in (espn_snapshot, football_snapshot) if item is not None]
        if not available:
            if allow_network and network_allowed_now:
                self._record_failure(errors)
            if allow_network and not network_allowed_now:
                raise DailyFixtureError("Zero-credit fixture sources are in temporary retry backoff")
            raise DailyFixtureError("All zero-credit fixture sources are unavailable: " + ", ".join(errors))
        frames = [item.fixtures for item in available if not item.fixtures.empty]
        combined = (
            pd.concat(frames, ignore_index=True)
            if frames else pd.DataFrame(columns=["date", "league", "home_team", "away_team", "fixture_date"])
        )
        if not combined.empty:
            combined = (
                combined.drop_duplicates(["date", "league", "home_team", "away_team"], keep="first")
                .sort_values(["date", "home_team"], kind="stable")
                .reset_index(drop=True)
            )
        snapshot = FixtureSnapshot(
            fixtures=combined, source=" + ".join(item.source for item in available),
            fetched_at=max(item.fetched_at for item in available),
            from_cache=all(item.from_cache for item in available),
            sha256=hashlib.sha256("|".join(item.sha256 for item in available).encode("utf-8")).hexdigest(),
        )
        self._clear_failure()
        return snapshot



def fixture_identifier(row: Mapping[str, Any]) -> str:
    date = pd.to_datetime(row.get("date"), utc=True, errors="coerce")
    # A fixture keeps the same identity when ESPN and Football-Data use
    # different aliases or when the advertised kick-off time moves within the
    # same match day. This prevents duplicate daily predictions after a source
    # fallback or schedule adjustment.
    date_token = "unknown" if pd.isna(date) else date.date().isoformat()
    home = football_model_name(str(row.get("home_team") or ""))
    away = football_model_name(str(row.get("away_team") or ""))
    raw = "|".join([
        str(row.get("league") or ""), date_token,
        normalize_identity(home),
        normalize_identity(away),
    ])
    return "free-fixture-" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def probability_diagnostics(probabilities: Mapping[str, Any], *, labels: Iterable[str] = ("home", "draw", "away")) -> dict[str, Any]:
    labels = tuple(labels)
    values: list[float] = []
    issues: list[str] = []
    for label in labels:
        try:
            value = float(probabilities[label])
        except (KeyError, TypeError, ValueError):
            issues.append(f"missing_or_invalid_{label}")
            continue
        values.append(value)
        if not math.isfinite(value):
            issues.append(f"non_finite_{label}")
        elif value < 0 or value > 1:
            issues.append(f"out_of_range_{label}")
    total = float(sum(values)) if len(values) == len(labels) else None
    if total is not None and not np.isclose(total, 1.0, atol=1e-6):
        issues.append("probabilities_do_not_sum_to_one")
    return {"valid": not issues, "issues": issues, "sum": total}


def build_model_diagnostics(
    *,
    model_loaded: bool,
    artifact_integrity_verified: bool,
    model_version: str,
    data_cutoff: Any,
    metrics: Mapping[str, Any] | None,
    model_freshness: Mapping[str, Any],
    probe_probabilities: Mapping[str, Any] | None,
    registry_status: str | None = None,
) -> dict[str, Any]:
    football_metrics = dict(metrics or {})
    probability_check = probability_diagnostics(probe_probabilities or {}) if probe_probabilities else {
        "valid": False, "issues": ["probe_prediction_unavailable"], "sum": None,
    }
    checks = {
        "model_loaded": bool(model_loaded),
        "artifact_integrity_verified": bool(artifact_integrity_verified),
        "probability_probe_valid": bool(probability_check["valid"]),
        "chronological_test_size_sufficient": int(football_metrics.get("n_test") or 0) >= 100,
        "finite_log_loss": math.isfinite(float(football_metrics.get("log_loss", float("nan")))),
        "beats_naive_log_loss": (
            math.isfinite(float(football_metrics.get("log_loss", float("nan"))))
            and math.isfinite(float(football_metrics.get("naive_log_loss", float("nan"))))
            and float(football_metrics["log_loss"]) < float(football_metrics["naive_log_loss"])
        ),
        "calibration_diagnostic_available": math.isfinite(float(football_metrics.get("ece", float("nan")))),
        "model_not_stale": not bool(model_freshness.get("stale", True)),
    }
    hard_failures = [name for name in ("model_loaded", "artifact_integrity_verified", "probability_probe_valid") if not checks[name]]
    warnings = [name for name, passed in checks.items() if not passed and name not in hard_failures]
    if hard_failures:
        status = "blocked"
    elif warnings:
        status = "degraded"
    else:
        status = "operational_research"
    betting_ready = False
    betting_blockers = [
        "no validated live-market evidence",
        "no automatic stake or bet placement",
    ]
    if registry_status not in {None, "active"}:
        betting_blockers.append(f"registry status is {registry_status}")
    return {
        "schema_version": "1.0",
        "status": status,
        "model_version": model_version,
        "registry_status": registry_status,
        "data_cutoff": None if pd.isna(pd.to_datetime(data_cutoff, utc=True, errors="coerce")) else pd.to_datetime(data_cutoff, utc=True).isoformat(),
        "freshness": dict(model_freshness),
        "checks": checks,
        "hard_failures": hard_failures,
        "warnings": warnings,
        "probability_probe": probability_check,
        "metrics": {
            key: football_metrics.get(key)
            for key in ("n_test", "log_loss", "naive_log_loss", "brier", "rps", "accuracy", "ece", "calibration_temperature")
        },
        "product_readiness": {
            "model_only_predictions": status != "blocked",
            "market_shortlist": betting_ready,
            "market_shortlist_blockers": betting_blockers,
        },
    }


def select_fixture_window(fixtures: pd.DataFrame, *, requested_date: str, horizon_days: int, leagues: Iterable[str]) -> pd.DataFrame:
    if fixtures.empty:
        return fixtures.copy()
    start = pd.Timestamp(requested_date, tz="UTC")
    end = start + pd.Timedelta(days=max(0, int(horizon_days)) + 1)
    allowed = {str(value).upper() for value in leagues}
    dates = pd.to_datetime(fixtures["date"], utc=True, errors="coerce")
    return fixtures[(fixtures["league"].astype(str).str.upper().isin(allowed)) & (dates >= start) & (dates < end)].copy()
