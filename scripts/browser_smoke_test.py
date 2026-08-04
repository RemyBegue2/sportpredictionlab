from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from typing import Any


def _write_report(path: str, payload: dict[str, Any]) -> None:
    if not path:
        return
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


# Regression contracts: dual-sport ROI lab did not render; coverage preflight did not render; deferred expert view did not render.
def main() -> None:
    parser = argparse.ArgumentParser(description="Open the deployed private UI in Chromium and fail on frontend errors.")
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--password", default=os.getenv("APP_PASSWORD", ""))
    parser.add_argument("--timeout-ms", type=int, default=45000)
    parser.add_argument("--long-session-seconds", type=int, default=0)
    parser.add_argument("--navigation-interval-ms", type=int, default=5000)
    parser.add_argument("--long-session-scenario", choices=["simple", "expert", "mixed"], default="mixed")
    parser.add_argument("--report-path", default="")
    args = parser.parse_args()

    if not args.password:
        raise SystemExit("APP_PASSWORD is required for the authenticated browser smoke test")
    if args.long_session_seconds < 0 or args.long_session_seconds > 3600:
        raise SystemExit("long-session-seconds must be between 0 and 3600")
    if args.navigation_interval_ms < 250:
        raise SystemExit("navigation-interval-ms must be at least 250")

    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise SystemExit("Install Playwright in the GitHub workflow before running this script") from exc

    console_errors: list[str] = []
    page_errors: list[str] = []
    report: dict[str, Any] = {
        "status": "failed",
        "expected_version": args.expected_version,
        "long_session_seconds": args.long_session_seconds,
        "long_session_scenario": args.long_session_scenario,
    }
    try:
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

            try:
                page.wait_for_function(
                    """() => {
                        const model = document.querySelector('#dailyModelStatus');
                        const detail = document.querySelector('#dailyPredictionDetail');
                        const today = document.querySelector('#dailySlate');
                        const upcoming = document.querySelector('#upcomingSlate');
                        const signals = document.querySelector('#researchSignals');
                        const learning = document.querySelector('#learningAction');
                        const evidence = document.querySelector('#evidenceAccelerationDetails');
                        const controlled = document.querySelector('#controlledDecisionDetails');
                        if (!model || !detail || !today || !upcoming || !signals || !learning || !evidence || !controlled) return false;
                        return !['', '—', 'Chargement…'].includes((model.textContent || '').trim())
                          && !(detail.textContent || '').includes('Aucun calendrier chargé')
                          && !today.querySelector('.loading-card')
                          && !upcoming.querySelector('.loading-card')
                          && !signals.querySelector('.loading-card')
                          && !(learning.textContent || '').includes('Évaluation des portes en cours')
                          && !(evidence.textContent || '').includes('non exécutée')
                          && !(controlled.textContent || '').includes('non exécuté');
                    }""",
                    timeout=args.timeout_ms,
                )
            except Exception as exc:
                toast = page.locator("#toast").inner_text().strip() if page.locator("#toast").count() else ""
                raise RuntimeError(
                    "evidence-aware compact view did not render"
                    + (f"; interface message: {toast}" if toast else "")
                ) from exc

            daily_model = page.locator("#dailyModelStatus").inner_text().strip()
            daily_count = page.locator("#dailyPredictionCount").inner_text().strip()
            today_action = page.locator("#todayAction").inner_text().strip()
            mode_label = page.locator("#interfaceMode").inner_text().strip()
            if mode_label != "Mode expert":
                raise RuntimeError(f"simple mode is not the default ({mode_label!r})")
            if not page.locator('[data-simple-panel="today"]').is_visible():
                raise RuntimeError("Today is not the default compact panel")
            if page.locator('[data-simple-panel="signals"]').is_visible() or page.locator('[data-simple-panel="learning"]').is_visible():
                raise RuntimeError("multiple compact panels are visible at once")
            if page.locator("#control").is_visible():
                raise RuntimeError("expert controls are visible in simple mode")

            page.click('[data-simple-target="signals"]')
            page.wait_for_function("() => document.querySelector('[data-simple-panel=\"signals\"]')?.classList.contains('is-active')", timeout=args.timeout_ms)
            research_signals = page.locator("#researchSignalCount").inner_text().strip()
            research_training = page.locator("#researchTraining").inner_text().strip()
            page.click('[data-simple-target="learning"]')
            page.wait_for_function("() => document.querySelector('[data-simple-panel=\"learning\"]')?.classList.contains('is-active')", timeout=args.timeout_ms)
            learning_status = page.locator("#learningChallenger").inner_text().strip()
            feature_reliability = page.locator("#featureReliability").inner_text().strip()
            challenger_football = page.locator("#learningFootballState").inner_text().strip()
            challenger_tennis = page.locator("#learningTennisState").inner_text().strip()
            session_status = page.locator("#sessionStatus").inner_text().strip()
            if page.locator("#dailySlate .slate-card").count() > 8 or page.locator("#researchSignals .slate-card").count() > 8:
                raise RuntimeError("compact card cap was exceeded")

            baseline = page.evaluate(
                """() => ({
                    dom_nodes: document.getElementsByTagName('*').length,
                    resources: performance.getEntriesByType('resource').length,
                    heap: performance.memory ? performance.memory.usedJSHeapSize : null
                })"""
            )
            navigation_cycles = 0
            duration = args.long_session_seconds
            quick_cycles = 10 if duration == 0 else 0
            deadline = time.monotonic() + duration
            if args.long_session_scenario == "expert" and page.locator("#interfaceMode").inner_text().strip() == "Mode expert":
                page.click("#interfaceMode")
                page.wait_for_function("() => document.body.classList.contains('expert-mode')", timeout=args.timeout_ms)
            while navigation_cycles < quick_cycles or (duration and time.monotonic() < deadline):
                page.click('[data-simple-target="today"]')
                page.click('[data-simple-target="signals"]')
                page.click('[data-simple-target="learning"]')
                navigation_cycles += 1
                if page.locator('[data-simple-panel].is-active').count() != 1:
                    raise RuntimeError("compact navigation accumulated active panels")
                if duration:
                    page.wait_for_timeout(args.navigation_interval_ms)
                    # Exercise expert lazy loading periodically without generating provider calls.
                    if args.long_session_scenario == "mixed" and navigation_cycles % 12 == 0:
                        page.click("#interfaceMode")
                        page.wait_for_timeout(300)
                        page.click("#interfaceMode")

            ending = page.evaluate(
                """() => ({
                    dom_nodes: document.getElementsByTagName('*').length,
                    resources: performance.getEntriesByType('resource').length,
                    heap: performance.memory ? performance.memory.usedJSHeapSize : null
                })"""
            )
            dom_growth = int(ending["dom_nodes"] - baseline["dom_nodes"])
            resource_growth = int(ending["resources"] - baseline["resources"])
            if dom_growth > 80:
                raise RuntimeError(f"unbounded DOM growth detected: +{dom_growth} nodes")
            allowed_resources = max(40, navigation_cycles * 2 + 20)
            if resource_growth > allowed_resources:
                raise RuntimeError(f"unbounded request growth detected: +{resource_growth} resources for {navigation_cycles} cycles")

            # Finish in expert mode and prove deferred diagnostics load on demand.
            # Failure message compatibility: deferred expert view did not render
            if page.locator("#interfaceMode").inner_text().strip() == "Mode expert":
                page.click("#interfaceMode")
            page.wait_for_function("() => document.body.classList.contains('expert-mode')", timeout=args.timeout_ms)
            page.wait_for_function(
                """() => {
                    const control = document.querySelector('#controlOverall');
                    const value = (control?.textContent || '').trim();
                    const evidence = document.querySelector('#evidenceGate');
                    const preflight = document.querySelector('#preflightDecision');
                    if (!control || !evidence || !preflight) return false;
                    return value !== '' && value !== '—'
                      && !['', '—'].includes((evidence.textContent || '').trim())
                      && !['', '—'].includes((preflight.textContent || '').trim());
                }""",
                timeout=args.timeout_ms,
            )
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
        if not daily_count or not today_action:
            problems.append("daily summary did not render")
        if not research_signals or not research_training:
            problems.append("dual-sport research lab did not render")
        if not learning_status or learning_status == "Chargement…":
            problems.append("learning status did not render")
        if "Football" not in feature_reliability or "Tennis" not in feature_reliability:
            problems.append("feature-lab reliability did not render")
        if not challenger_football or not challenger_tennis or not session_status:
            problems.append("challenger or session state did not render")
        if not control or not evidence or not preflight:
            problems.append("expert diagnostics did not render")
        if toast.startswith("Interface partiellement chargée"):
            problems.append("partial interface error: " + toast)
        known_noise = ("favicon.ico",)
        console_errors = [item for item in console_errors if not any(noise in item for noise in known_noise)]
        if console_errors:
            problems.append("console errors: " + " | ".join(console_errors))
        if page_errors:
            problems.append("page errors: " + " | ".join(page_errors))
        if problems:
            raise RuntimeError("; ".join(problems))

        report.update({
            "status": "ok",
            "health": health,
            "daily_model": daily_model,
            "daily_predictions": daily_count,
            "today_action": today_action,
            "research_signals": research_signals,
            "learning_status": learning_status,
            "feature_reliability": feature_reliability,
            "challenger_football": challenger_football,
            "challenger_tennis": challenger_tennis,
            "session_status": session_status,
            "navigation_cycles": navigation_cycles,
            "baseline": baseline,
            "ending": ending,
            "dom_growth": dom_growth,
            "resource_growth": resource_growth,
            "one_compact_panel_at_a_time": True,
            "expert_mode_lazy_loaded": True,
            "control_center": control,
            "evidence": evidence,
            "preflight": preflight,
        })
    except Exception as exc:
        report["error"] = str(exc)
        report["console_errors"] = console_errors
        report["page_errors"] = page_errors
        _write_report(args.report_path, report)
        raise SystemExit("Browser smoke test failed: " + str(exc)) from exc

    _write_report(args.report_path, report)
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
