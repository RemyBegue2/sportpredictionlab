from __future__ import annotations

import argparse
import os
from urllib.parse import urljoin

import requests


def main() -> int:
    p = argparse.ArgumentParser(description="Verify a deployed V3.1 instance without exposing secrets.")
    p.add_argument("base_url")
    p.add_argument("--password", default=os.getenv("APP_PASSWORD"))
    args = p.parse_args()
    base = args.base_url.rstrip("/") + "/"
    session = requests.Session()

    health = session.get(urljoin(base, "api/health"), timeout=20)
    health.raise_for_status()
    print("health", health.json().get("status"), health.json().get("version"))

    if args.password:
        login = session.post(urljoin(base, "api/auth/login"), json={"password": args.password}, timeout=20)
        login.raise_for_status()
        csrf = login.json().get("csrf_token")
    else:
        csrf = None

    auth = session.get(urljoin(base, "api/auth/status"), timeout=20)
    auth.raise_for_status()
    if not auth.json().get("authenticated"):
        raise RuntimeError("Deployment requires authentication; provide APP_PASSWORD or --password")

    ready = session.get(urljoin(base, "api/ready"), timeout=20)
    if ready.status_code != 200:
        raise RuntimeError(f"Deployment not ready: {ready.json().get('issues')}")
    catalog = session.get(urljoin(base, "api/catalog"), timeout=20)
    catalog.raise_for_status()
    history = session.get(urljoin(base, "api/history/predictions?limit=1"), timeout=20)
    history.raise_for_status()
    print("ready", ready.json().get("status"), "football_teams", len(catalog.json().get("football_teams", [])))

    if csrf:
        logout = session.post(urljoin(base, "api/auth/logout"), headers={"X-CSRF-Token": csrf}, timeout=20)
        logout.raise_for_status()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
