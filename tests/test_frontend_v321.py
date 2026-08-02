from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_empty_benchmark_ci_is_guarded_before_to_fixed() -> None:
    js = (ROOT / "static" / "app.js").read_text(encoding="utf-8")
    assert "ci.length===2" in js
    assert "const hasValidCi=" in js
    assert "hasValidCi?`IC 95 %" in js


def test_health_badge_is_not_downgraded_by_secondary_render_error() -> None:
    js = (ROOT / "static" / "app.js").read_text(encoding="utf-8")
    assert "Interface partiellement chargée" in js
    assert "$('#health').textContent='API indisponible'" in js
    # The health failure branch returns before the secondary initialization block.
    assert "toast(e.message);\n    return;" in js
