from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hmac
import secrets
from typing import Deque

from fastapi import Request
from fastapi.responses import JSONResponse, RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from .cloud_config import CloudSettings


@dataclass(frozen=True)
class LoginDecision:
    allowed: bool
    retry_after_seconds: int = 0


class LoginRateLimiter:
    def __init__(self, max_attempts: int = 6, window_minutes: int = 15) -> None:
        self.max_attempts = max_attempts
        self.window = timedelta(minutes=window_minutes)
        self._attempts: dict[str, Deque[datetime]] = defaultdict(deque)

    def check(self, key: str, *, now: datetime | None = None) -> LoginDecision:
        current = now or datetime.now(timezone.utc)
        queue = self._attempts[key]
        while queue and current - queue[0] > self.window:
            queue.popleft()
        if len(queue) < self.max_attempts:
            return LoginDecision(True)
        retry = max(1, int((self.window - (current - queue[0])).total_seconds()))
        return LoginDecision(False, retry)

    def fail(self, key: str, *, now: datetime | None = None) -> None:
        self._attempts[key].append(now or datetime.now(timezone.utc))

    def success(self, key: str) -> None:
        self._attempts.pop(key, None)


LOGIN_LIMITER = LoginRateLimiter()


def client_key(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "").split(",", 1)[0].strip()
    return forwarded or (request.client.host if request.client else "unknown")


def verify_password(candidate: str, settings: CloudSettings) -> bool:
    expected = settings.app_password or ""
    return bool(expected) and hmac.compare_digest(candidate.encode("utf-8"), expected.encode("utf-8"))


def establish_session(request: Request) -> str:
    csrf = secrets.token_urlsafe(24)
    request.session.clear()
    request.session.update({"authenticated": True, "csrf": csrf, "issued_at": datetime.now(timezone.utc).isoformat()})
    return csrf


def clear_session(request: Request) -> None:
    request.session.clear()


class AuthenticationGateMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, settings: CloudSettings) -> None:
        super().__init__(app)
        self.settings = settings
        self.public_exact = {"/login", "/api/health", "/api/auth/login"}
        self.public_prefixes = ("/static/",)

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if not self.settings.auth_required:
            request.state.authenticated = True
            return await call_next(request)
        path = request.url.path
        if path in self.public_exact or path.startswith(self.public_prefixes):
            return await call_next(request)
        authenticated = bool(request.session.get("authenticated"))
        if not authenticated:
            if path.startswith("/api/") or path.startswith("/docs") or path.startswith("/redoc") or path == "/openapi.json":
                return JSONResponse({"detail": "Authentication required"}, status_code=401)
            return RedirectResponse(url=f"/login?next={path}", status_code=303)
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            expected = str(request.session.get("csrf", ""))
            supplied = request.headers.get("x-csrf-token", "")
            if not expected or not hmac.compare_digest(expected, supplied):
                return JSONResponse({"detail": "Invalid CSRF token"}, status_code=403)
        request.state.authenticated = True
        return await call_next(request)
