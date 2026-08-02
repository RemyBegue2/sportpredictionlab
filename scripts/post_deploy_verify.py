from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request


def fetch_json(url: str, timeout: float) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": "sports-prediction-lab-deploy-verifier/3.5"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify the public Railway deployment evidence endpoint.")
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--expected-commit")
    parser.add_argument("--expected-model-sha256")
    parser.add_argument("--attempts", type=int, default=18)
    parser.add_argument("--delay-seconds", type=float, default=10.0)
    parser.add_argument("--timeout", type=float, default=8.0)
    args = parser.parse_args()

    url = args.base_url.rstrip("/") + "/api/release"
    last_error: str | None = None
    for attempt in range(1, max(1, args.attempts) + 1):
        try:
            payload = fetch_json(url, args.timeout)
            problems: list[str] = []
            if payload.get("version") != args.expected_version:
                problems.append(f"version {payload.get('version')} != {args.expected_version}")
            actual_commit = str(payload.get("source_commit") or "")
            if args.expected_commit and not actual_commit.startswith(args.expected_commit):
                problems.append(f"commit {actual_commit or 'unknown'} does not match {args.expected_commit}")
            actual_model = str(payload.get("football_model_sha256") or "")
            if args.expected_model_sha256 and actual_model != args.expected_model_sha256:
                problems.append("football model hash mismatch")
            if payload.get("artifact_integrity_ok") is not True:
                problems.append("artifact integrity is not verified")
            if not problems:
                print(json.dumps({"status": "verified", "attempt": attempt, "proof": payload}, ensure_ascii=False))
                return
            last_error = "; ".join(problems)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_error = f"{type(exc).__name__}: {exc}"
        if attempt < args.attempts:
            time.sleep(max(0.0, args.delay_seconds))
    raise SystemExit(f"Deployment verification failed after {args.attempts} attempts: {last_error}")


if __name__ == "__main__":
    main()
