from __future__ import annotations

import argparse
import json
import os


def main() -> None:
    parser = argparse.ArgumentParser(description="Open the deployed private UI in Chromium and fail on frontend errors.")
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--password", default=os.getenv("APP_PASSWORD", ""))
    parser.add_argument("--timeout-ms", type=int, default=45000)
    args = parser.parse_args()

    if not args.password:
        raise SystemExit("APP_PASSWORD is required for the authenticated browser smoke test")

    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise SystemExit("Install Playwright in the GitHub workflow before running this script") from exc

    console_errors: list[str] = []
    page_errors: list[str] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.on("console", lambda message: console_errors.append(message.text) if message.type == "error" else None)
        page.on("pageerror", lambda error: page_errors.append(str(error)))
        page.goto(args.base_url.rstrip("/") + "/", wait_until="domcontentloaded", timeout=args.timeout_ms)
        if "/login" in page.url:
            page.fill("#password", args.password)
            page.click("button[type=submit]")
            page.wait_for_url(lambda url: "/login" not in url, timeout=args.timeout_ms)
        page.wait_for_selector("#health.ok", timeout=args.timeout_ms)
        health = page.locator("#health").inner_text()

        # Le badge santé est rendu avant les appels secondaires. Attendre le
        # contenu réel du centre de contrôle évite un faux négatif de course.
        try:
            page.wait_for_function(
                """() => {
                    const element = document.querySelector('#controlOverall');
                    if (!element) return false;
                    const value = (element.textContent || '').trim();
                    return value.length > 0 && value !== '—';
                }""",
                timeout=args.timeout_ms,
            )
        except Exception as exc:
            toast = page.locator("#toast").inner_text().strip() if page.locator("#toast").count() else ""
            raise SystemExit(
                "Browser smoke test failed: control center did not render"
                + (f"; interface message: {toast}" if toast else "")
            ) from exc

        control = page.locator("#controlOverall").inner_text().strip()
        try:
            page.wait_for_function(
                """() => {
                    const element = document.querySelector('#evidenceGate');
                    if (!element) return false;
                    const value = (element.textContent || '').trim();
                    return value.length > 0 && value !== '—';
                }""",
                timeout=args.timeout_ms,
            )
        except Exception as exc:
            raise SystemExit("Browser smoke test failed: evidence dashboard did not render") from exc
        evidence = page.locator("#evidenceGate").inner_text().strip()
        browser.close()

    expected = f"v{args.expected_version}"
    problems: list[str] = []
    if expected not in health:
        problems.append(f"health badge mismatch: {health!r}")
    if not control or control == "—":
        problems.append("control center did not render")
    if not evidence or evidence == "—":
        problems.append("evidence dashboard did not render")
    known_noise = ("favicon.ico",)
    console_errors = [item for item in console_errors if not any(noise in item for noise in known_noise)]
    if console_errors:
        problems.append("console errors: " + " | ".join(console_errors))
    if page_errors:
        problems.append("page errors: " + " | ".join(page_errors))
    if problems:
        raise SystemExit("Browser smoke test failed: " + "; ".join(problems))
    print(json.dumps({"status": "ok", "health": health, "control_center": control, "evidence": evidence}, ensure_ascii=False))


if __name__ == "__main__":
    main()
