from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request


def fetch_json(url: str, timeout: float) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": "sports-prediction-lab-deploy-verifier/4.1"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify Railway readiness and public release evidence.")
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--expected-commit")
    parser.add_argument("--expected-model-sha256")
    parser.add_argument("--attempts", type=int, default=18)
    parser.add_argument("--delay-seconds", type=float, default=10.0)
    parser.add_argument("--timeout", type=float, default=8.0)
    args = parser.parse_args()

    base = args.base_url.rstrip("/")
    last_error: str | None = None
    for attempt in range(1, max(1, args.attempts) + 1):
        try:
            readiness = fetch_json(base + "/api/ready", args.timeout)
            release = fetch_json(base + "/api/release", args.timeout)
            problems: list[str] = []
            if readiness.get("status") != "ready":
                problems.append("application readiness is not verified")
            if readiness.get("version") != args.expected_version:
                problems.append(f"readiness version {readiness.get('version')} != {args.expected_version}")
            if release.get("version") != args.expected_version:
                problems.append(f"release version {release.get('version')} != {args.expected_version}")
            actual_commit = str(release.get("source_commit") or "")
            if args.expected_commit and not actual_commit.startswith(args.expected_commit):
                problems.append(f"commit {actual_commit or 'unknown'} does not match {args.expected_commit}")
            actual_model = str(release.get("football_model_sha256") or "")
            if args.expected_model_sha256 and actual_model != args.expected_model_sha256:
                problems.append("football model hash mismatch")
            if release.get("artifact_integrity_ok") is not True:
                problems.append("artifact integrity is not verified")
            if release.get("automatic_model_promotion") is not False:
                problems.append("automatic model promotion must remain disabled")
            if release.get("profitability_claim") is not False:
                problems.append("profitability claim flag must remain false")
            if release.get("automatic_bet_placement") is not False:
                problems.append("automatic bet placement must remain disabled")
            if release.get("daily_model_only_enabled") is not True:
                problems.append("zero-credit daily model mode must be enabled")
            if release.get("daily_odds_enabled") is not False:
                problems.append("daily paid odds must remain disabled for V4.3 deployment")
            if release.get("historical_evidence_enabled") is not False:
                problems.append("historical paid evidence must remain disabled for V4.3 deployment")
            if not problems:
                print(json.dumps({"status": "verified", "attempt": attempt, "readiness": readiness, "proof": release}, ensure_ascii=False))
                return
            last_error = "; ".join(problems)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_error = f"{type(exc).__name__}: {exc}"
        if attempt < args.attempts:
            time.sleep(max(0.0, args.delay_seconds))
    raise SystemExit(f"Deployment verification failed after {args.attempts} attempts: {last_error}")


if __name__ == "__main__":
    main()
