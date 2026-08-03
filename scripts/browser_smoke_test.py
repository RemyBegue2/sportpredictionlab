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

        # V4.5 starts in a simple view and defers expert endpoints until the
        # operator explicitly opens them.
        try:
            page.wait_for_function(
                """() => {
                    const model = document.querySelector('#dailyModelStatus');
                    const detail = document.querySelector('#dailyPredictionDetail');
                    const today = document.querySelector('#dailySlate');
                    const upcoming = document.querySelector('#upcomingSlate');
                    const signals = document.querySelector('#researchSignals');
                    const learning = document.querySelector('#learningAction');
                    if (!model || !detail || !today || !upcoming || !signals || !learning) return false;
                    return !['', '—', 'Chargement…'].includes((model.textContent || '').trim())
                      && !(detail.textContent || '').includes('Aucun calendrier chargé')
                      && !today.querySelector('.loading-card')
                      && !upcoming.querySelector('.loading-card')
                      && !signals.querySelector('.loading-card')
                      && !(learning.textContent || '').includes('Évaluation des portes en cours');
                }""",
                timeout=args.timeout_ms,
            )
        except Exception as exc:
            toast = page.locator("#toast").inner_text().strip() if page.locator("#toast").count() else ""
            raise SystemExit(
                "Browser smoke test failed: dual-sport ROI lab did not render in simple daily view"
                + (f"; interface message: {toast}" if toast else "")
            ) from exc

        daily_model = page.locator("#dailyModelStatus").inner_text().strip()
        daily_count = page.locator("#dailyPredictionCount").inner_text().strip()
        research_signals = page.locator("#researchSignalCount").inner_text().strip()
        research_training = page.locator("#researchTraining").inner_text().strip()
        learning_status = page.locator("#learningChallenger").inner_text().strip()
        mode_label = page.locator("#interfaceMode").inner_text().strip()
        if mode_label != "Mode expert":
            raise SystemExit(f"Browser smoke test failed: simple mode is not the default ({mode_label!r})")
        if page.locator("#control").is_visible():
            raise SystemExit("Browser smoke test failed: expert controls are visible in simple mode")

        # Toggle expert mode and prove that deferred diagnostics load on demand.
        page.click("#interfaceMode")
        page.wait_for_function("() => document.body.classList.contains('expert-mode')", timeout=args.timeout_ms)
        try:
            page.wait_for_function(
                """() => {
                    const control = document.querySelector('#controlOverall');
                    const evidence = document.querySelector('#evidenceGate');
                    const preflight = document.querySelector('#preflightDecision');
                    if (!control || !evidence || !preflight) return false;
                    const value = (control.textContent || '').trim();
                    return value.length > 0 && value !== '—'
                      && !['', '—'].includes((evidence.textContent || '').trim())
                      && !['', '—'].includes((preflight.textContent || '').trim());
                }""",
                timeout=args.timeout_ms,
            )
        except Exception as exc:
            toast = page.locator("#toast").inner_text().strip() if page.locator("#toast").count() else ""
            raise SystemExit(
                "Browser smoke test failed: deferred expert view did not render"
                + (f"; interface message: {toast}" if toast else "")
            ) from exc
        control = page.locator("#controlOverall").inner_text().strip()
        evidence = page.locator("#evidenceGate").inner_text().strip()
        preflight = page.locator("#preflightDecision").inner_text().strip()
        toast = page.locator("#toast").inner_text().strip() if page.locator("#toast").count() else ""
        browser.close()

    expected = f"v{args.expected_version}"
    problems: list[str] = []
    if expected not in health:
        problems.append(f"health badge mismatch: {health!r}")
    if not daily_model or daily_model in {"—", "Chargement…"}:
        problems.append("daily model diagnostics did not render")
    if not daily_count:
        problems.append("daily prediction count did not render")
    if not research_signals:
        problems.append("dual-sport research signal count did not render")
    if not research_training:
        problems.append("dual-sport ROI training status did not render")
    if not learning_status or learning_status == "Chargement…":
        problems.append("champion/challenger learning status did not render")
    if not control or control == "—":
        problems.append("control center did not render after expert toggle")
    if not evidence or evidence == "—":
        problems.append("evidence dashboard did not render after expert toggle")
    if not preflight or preflight == "—":
        problems.append("coverage preflight did not render after expert toggle")
    if toast.startswith("Interface partiellement chargée"):
        problems.append("partial interface error: " + toast)
    known_noise = ("favicon.ico",)
    console_errors = [item for item in console_errors if not any(noise in item for noise in known_noise)]
    if console_errors:
        problems.append("console errors: " + " | ".join(console_errors))
    if page_errors:
        problems.append("page errors: " + " | ".join(page_errors))
    if problems:
        raise SystemExit("Browser smoke test failed: " + "; ".join(problems))
    print(json.dumps({
        "status": "ok",
        "health": health,
        "daily_model": daily_model,
        "daily_predictions": daily_count,
        "research_signals": research_signals,
        "research_training_rendered": bool(research_training),
        "learning_status": learning_status,
        "simple_mode_default": True,
        "expert_mode_lazy_loaded": True,
        "control_center": control,
        "evidence": evidence,
        "preflight": preflight,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
