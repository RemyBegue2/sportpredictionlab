from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import time
from typing import Any, Iterable, Sequence

import requests


_API_HOST = "https://api.the-odds-api.com"
_TOKEN_RE = re.compile(r"^[A-Za-z0-9_\-]+$")


class OddsApiError(RuntimeError):
    """Base exception for The Odds API integration."""


class OddsApiNotConfigured(OddsApiError):
    """Raised when no server-side API key is configured."""


class OddsApiQuotaError(OddsApiError):
    """Raised when the provider reports exhausted quota or rate limiting."""


class OddsApiNetworkDisabled(OddsApiError):
    """Raised when a cache miss would require a paid provider call."""


@dataclass(frozen=True)
class QuotaUsage:
    remaining: int | None = None
    used: int | None = None
    last_cost: int | None = None

    @classmethod
    def from_headers(cls, headers: requests.structures.CaseInsensitiveDict | dict[str, str]) -> "QuotaUsage":
        def parse(name: str) -> int | None:
            raw = headers.get(name)
            try:
                return int(raw) if raw is not None else None
            except (TypeError, ValueError):
                return None

        return cls(
            remaining=parse("x-requests-remaining"),
            used=parse("x-requests-used"),
            last_cost=parse("x-requests-last"),
        )


@dataclass(frozen=True)
class OddsApiEnvelope:
    payload: Any
    quota: QuotaUsage
    fetched_at: str
    from_cache: bool
    request_fingerprint: str


@dataclass(frozen=True)
class OddsApiConfig:
    api_key: str | None
    base_url: str = _API_HOST
    timeout_seconds: float = 20.0
    max_retries: int = 3
    cache_dir: Path = Path("data/odds_api/cache")
    user_agent: str = "sports-prediction-lab/0.3.5"

    @classmethod
    def from_env(cls, *, root: Path | None = None) -> "OddsApiConfig":
        cache_root = root or Path.cwd()
        return cls(
            api_key=os.getenv("THE_ODDS_API_KEY") or None,
            timeout_seconds=float(os.getenv("THE_ODDS_API_TIMEOUT", "20")),
            max_retries=int(os.getenv("THE_ODDS_API_RETRIES", "3")),
            cache_dir=cache_root / os.getenv("THE_ODDS_API_CACHE", "data/odds_api/cache"),
        )

    @property
    def configured(self) -> bool:
        return bool(self.api_key)


class OddsApiClient:
    """Small, cache-aware, server-side client for The Odds API v4.

    The API key is appended only at request time and is never written to cache,
    returned to callers, or included in exception messages.
    """

    def __init__(self, config: OddsApiConfig, *, session: requests.Session | None = None):
        if config.base_url.rstrip("/") != _API_HOST:
            raise ValueError("The Odds API host is fixed for SSRF protection")
        self.config = config
        self.session = session or requests.Session()
        self.config.cache_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def estimate_quota_cost(
        *,
        markets: Sequence[str] = ("h2h",),
        regions: Sequence[str] | None = None,
        bookmakers: Sequence[str] | None = None,
        historical: bool = False,
        snapshot_count: int = 1,
    ) -> int:
        if snapshot_count < 0:
            raise ValueError("snapshot_count must be non-negative")
        market_count = len(set(markets))
        if market_count < 1:
            raise ValueError("At least one market is required")
        if regions and bookmakers:
            raise ValueError("Use regions or bookmakers, not both")
        if bookmakers:
            source_groups = math.ceil(len(set(bookmakers)) / 10)
        else:
            source_groups = len(set(regions or ("eu",)))
        multiplier = 10 if historical else 1
        return snapshot_count * multiplier * market_count * max(1, source_groups)

    def _require_key(self) -> str:
        if not self.config.api_key:
            raise OddsApiNotConfigured(
                "THE_ODDS_API_KEY is not configured on the server. "
                "Set it as an environment variable; do not expose it in the browser."
            )
        return self.config.api_key

    @staticmethod
    def _validate_tokens(values: Iterable[str], *, label: str) -> list[str]:
        cleaned = []
        for value in values:
            token = str(value).strip()
            if not token or not _TOKEN_RE.fullmatch(token):
                raise ValueError(f"Invalid {label}: {value!r}")
            cleaned.append(token)
        return cleaned

    def _fingerprint(self, path: str, params: dict[str, Any]) -> str:
        safe = {k: v for k, v in sorted(params.items()) if k != "apiKey"}
        raw = json.dumps({"path": path, "params": safe}, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _cache_path(self, fingerprint: str) -> Path:
        return self.config.cache_dir / f"{fingerprint}.json"

    def _quota_path(self) -> Path:
        return self.config.cache_dir / "quota_status.json"

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    def quota_status(self) -> dict[str, Any]:
        path = self._quota_path()
        if not path.exists():
            return {"known": False, "remaining": None, "used": None, "last_cost": None, "updated_at": None}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"known": False, "remaining": None, "used": None, "last_cost": None, "updated_at": None}

    def _write_json_atomic(self, path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)

    def _read_cache(self, fingerprint: str, max_age_seconds: float | None) -> OddsApiEnvelope | None:
        path = self._cache_path(fingerprint)
        if not path.exists():
            return None
        try:
            cached = json.loads(path.read_text(encoding="utf-8"))
            fetched = datetime.fromisoformat(cached["fetched_at"].replace("Z", "+00:00"))
        except (OSError, KeyError, ValueError, json.JSONDecodeError):
            return None
        if max_age_seconds is not None:
            age = (datetime.now(timezone.utc) - fetched.astimezone(timezone.utc)).total_seconds()
            if age > max_age_seconds:
                return None
        quota = QuotaUsage(**cached.get("quota", {}))
        return OddsApiEnvelope(
            payload=cached["payload"],
            quota=quota,
            fetched_at=cached["fetched_at"],
            from_cache=True,
            request_fingerprint=fingerprint,
        )

    def _request(
        self,
        path: str,
        params: dict[str, Any],
        *,
        cache_ttl_seconds: float | None,
        force_refresh: bool = False,
        allow_network: bool = True,
    ) -> OddsApiEnvelope:
        api_key = self._require_key()
        if not path.startswith("/v4/") or ".." in path:
            raise ValueError("Invalid API path")
        fingerprint = self._fingerprint(path, params)
        if not force_refresh:
            cached = self._read_cache(fingerprint, cache_ttl_seconds)
            if cached is not None:
                return cached
        if not allow_network:
            raise OddsApiNetworkDisabled(
                "Paid provider network calls are disabled. A cached response was not available."
            )

        request_params = dict(params)
        request_params["apiKey"] = api_key
        url = f"{self.config.base_url}{path}"
        last_error: str | None = None
        response: requests.Response | None = None
        for attempt in range(self.config.max_retries + 1):
            try:
                response = self.session.get(
                    url,
                    params=request_params,
                    headers={"Accept": "application/json", "User-Agent": self.config.user_agent},
                    timeout=self.config.timeout_seconds,
                )
            except requests.RequestException as exc:
                last_error = exc.__class__.__name__
                if attempt >= self.config.max_retries:
                    raise OddsApiError(f"The Odds API request failed: {last_error}") from exc
                time.sleep(min(2**attempt, 4))
                continue

            if response.status_code == 429:
                if attempt >= self.config.max_retries:
                    raise OddsApiQuotaError("The Odds API rate limit was reached (HTTP 429)")
                retry_after = response.headers.get("Retry-After")
                try:
                    delay = min(float(retry_after), 10.0) if retry_after else min(2**attempt, 4)
                except ValueError:
                    delay = min(2**attempt, 4)
                time.sleep(delay)
                continue
            if response.status_code >= 500 and attempt < self.config.max_retries:
                time.sleep(min(2**attempt, 4))
                continue
            break

        if response is None:
            raise OddsApiError(f"The Odds API request failed: {last_error or 'unknown error'}")

        quota = QuotaUsage.from_headers(response.headers)
        quota_payload = {**asdict(quota), "known": any(x is not None for x in asdict(quota).values()), "updated_at": self._now_iso()}
        self._write_json_atomic(self._quota_path(), quota_payload)

        def provider_error_detail() -> str:
            try:
                body = response.json()
            except (TypeError, ValueError):
                return "no structured provider error was returned"
            if not isinstance(body, dict):
                return "no structured provider error was returned"
            code = str(body.get("error_code") or body.get("code") or "").strip()
            message = str(body.get("message") or body.get("detail") or body.get("error") or "").strip()
            parts = []
            if code:
                parts.append(code)
            if message and message != code:
                parts.append(message)
            return ": ".join(parts) if parts else "no structured provider error was returned"

        if response.status_code in {401, 403}:
            raise OddsApiError(
                "The Odds API rejected credentials or subscription access: "
                f"{provider_error_detail()}"
            )
        if response.status_code == 422:
            raise OddsApiError(
                "The Odds API rejected request parameters: "
                f"{provider_error_detail()}"
            )
        if response.status_code >= 400:
            raise OddsApiError(
                f"The Odds API returned HTTP {response.status_code}: {provider_error_detail()}"
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise OddsApiError("The Odds API returned invalid JSON") from exc

        fetched_at = self._now_iso()
        cache_payload = {
            "fetched_at": fetched_at,
            "path": path,
            "params": {k: v for k, v in params.items() if k != "apiKey"},
            "quota": asdict(quota),
            "payload": payload,
        }
        self._write_json_atomic(self._cache_path(fingerprint), cache_payload)
        return OddsApiEnvelope(
            payload=payload,
            quota=quota,
            fetched_at=fetched_at,
            from_cache=False,
            request_fingerprint=fingerprint,
        )

    @staticmethod
    def _common_params(
        *,
        markets: Sequence[str],
        regions: Sequence[str] | None,
        bookmakers: Sequence[str] | None,
    ) -> dict[str, Any]:
        market_tokens = OddsApiClient._validate_tokens(markets, label="market")
        if regions and bookmakers:
            raise ValueError("Use regions or bookmakers, not both")
        params: dict[str, Any] = {"markets": ",".join(market_tokens), "oddsFormat": "decimal", "dateFormat": "iso"}
        if bookmakers:
            params["bookmakers"] = ",".join(OddsApiClient._validate_tokens(bookmakers, label="bookmaker"))
        else:
            params["regions"] = ",".join(OddsApiClient._validate_tokens(regions or ("eu",), label="region"))
        return params

    def list_sports(self, *, include_inactive: bool = False, force_refresh: bool = False, allow_network: bool = True) -> OddsApiEnvelope:
        return self._request(
            "/v4/sports",
            {"all": "true" if include_inactive else "false"},
            cache_ttl_seconds=3600,
            force_refresh=force_refresh,
            allow_network=allow_network,
        )

    def current_odds(
        self,
        sport_key: str,
        *,
        markets: Sequence[str] = ("h2h",),
        regions: Sequence[str] | None = None,
        bookmakers: Sequence[str] | None = ("winamax_fr",),
        commence_time_from: str | None = None,
        commence_time_to: str | None = None,
        include_links: bool = False,
        force_refresh: bool = False,
        allow_network: bool = True,
    ) -> OddsApiEnvelope:
        sport = self._validate_tokens((sport_key,), label="sport key")[0]
        params = self._common_params(markets=markets, regions=regions, bookmakers=bookmakers)
        if commence_time_from:
            params["commenceTimeFrom"] = commence_time_from
        if commence_time_to:
            params["commenceTimeTo"] = commence_time_to
        if include_links:
            params["includeLinks"] = "true"
        return self._request(
            f"/v4/sports/{sport}/odds",
            params,
            cache_ttl_seconds=90,
            force_refresh=force_refresh,
            allow_network=allow_network,
        )

    def historical_odds(
        self,
        sport_key: str,
        *,
        snapshot_at: str,
        markets: Sequence[str] = ("h2h",),
        regions: Sequence[str] | None = None,
        bookmakers: Sequence[str] | None = ("winamax_fr",),
        force_refresh: bool = False,
    ) -> OddsApiEnvelope:
        sport = self._validate_tokens((sport_key,), label="sport key")[0]
        params = self._common_params(markets=markets, regions=regions, bookmakers=bookmakers)
        params["date"] = snapshot_at
        return self._request(
            f"/v4/historical/sports/{sport}/odds",
            params,
            cache_ttl_seconds=None,
            force_refresh=force_refresh,
        )

    def historical_events(
        self,
        sport_key: str,
        *,
        snapshot_at: str,
        force_refresh: bool = False,
    ) -> OddsApiEnvelope:
        """Return the provider's historical event list at one snapshot.

        The historical-events endpoint documents only the ``date`` query
        parameter in addition to the API key. Event commence-time filtering is
        therefore performed locally by the discovery script rather than sent
        as unsupported provider parameters.
        """
        sport = self._validate_tokens((sport_key,), label="sport key")[0]
        return self._request(
            f"/v4/historical/sports/{sport}/events",
            {"date": snapshot_at},
            cache_ttl_seconds=None,
            force_refresh=force_refresh,
        )

    def scores(
        self,
        sport_key: str,
        *,
        days_from: int | None = 3,
        event_ids: Sequence[str] | None = None,
        force_refresh: bool = False,
    ) -> OddsApiEnvelope:
        sport = self._validate_tokens((sport_key,), label="sport key")[0]
        params: dict[str, Any] = {"dateFormat": "iso"}
        if days_from is not None:
            if int(days_from) not in {1, 2, 3}:
                raise ValueError("days_from must be 1, 2, 3 or None")
            params["daysFrom"] = int(days_from)
        if event_ids:
            params["eventIds"] = ",".join(self._validate_tokens(event_ids, label="event id"))
        return self._request(
            f"/v4/sports/{sport}/scores",
            params,
            cache_ttl_seconds=60,
            force_refresh=force_refresh,
        )

