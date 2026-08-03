from __future__ import annotations

from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]


def test_percentage_formatter_is_shared_by_evidence_and_preflight() -> None:
    source = (ROOT / "static" / "app.js").read_text(encoding="utf-8")
    formatter = "const pct = (value) => Number.isFinite(Number(value))"
    assert source.count(formatter) == 1
    assert source.index(formatter) < source.index("function renderEvidence")
    assert "pct(report.baseline_coverage)" in source


def test_preflight_renderer_executes_without_reference_error() -> None:
    script = r"""
const fs = require('fs');
const vm = require('vm');
const elements = new Map();
function element(selector) {
  if (!elements.has(selector)) {
    elements.set(selector, {
      textContent: '', innerHTML: '', value: '', hidden: false, disabled: false,
      className: '', options: [],
      classList: {add(){}, remove(){}, toggle(){}, contains(){return false;}},
      addEventListener(){}, removeEventListener(){}, focus(){},
    });
  }
  return elements.get(selector);
}
const context = {
  console,
  document: {querySelector: element},
  window: {location: {assign(){}}},
  setTimeout(){},
  Headers,
  fetch: async () => ({ok: true, status: 200, json: async () => ({})}),
};
vm.createContext(context);
vm.runInContext(fs.readFileSync('static/app.js', 'utf8').replace(/\ninit\(\);\s*\n/, '\n'), context);
vm.runInContext(`renderPreflight({report: {
  decision: 'VIABLE', baseline_coverage: 0.75,
  baseline_coverage_ci95_low: 0.60, baseline_coverage_ci95_high: 0.86,
  recommended_selected_events: 45, preflight_credits: 12,
  maximum_preflight_credits: 120,
  candidate_campaign_plan: {candidate_plan_id: 'CPP-TEST'}
}})`, context);
if (elements.get('#preflightCoverage').textContent !== '75.0 %') process.exit(2);
if (!elements.get('#preflightInterval').textContent.includes('60.0 %')) process.exit(3);
"""
    result = subprocess.run(
        ["node", "-e", script],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout


def test_browser_smoke_rejects_partial_interface_toast() -> None:
    source = (ROOT / "scripts" / "browser_smoke_test.py").read_text(encoding="utf-8")
    assert "coverage preflight did not render" in source
    assert 'toast.startswith("Interface partiellement chargée")' in source
