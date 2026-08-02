from __future__ import annotations

from pathlib import Path
import re

from sports_predictor.release_registry import APP_VERSION


ROOT = Path(__file__).resolve().parents[1]


def test_all_static_id_selectors_exist_in_html() -> None:
    javascript = (ROOT / "static" / "app.js").read_text(encoding="utf-8")
    html = (ROOT / "static" / "index.html").read_text(encoding="utf-8")

    referenced_ids = set(re.findall(r"\$\('#([^']+)'\)", javascript))
    declared_ids = set(re.findall(r'id="([^"]+)"', html))

    missing = sorted(referenced_ids - declared_ids)
    assert missing == [], f"JavaScript references missing HTML ids: {missing}"


def test_frontend_cache_bust_matches_release() -> None:
    html = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
    assert f'/static/app.js?v={APP_VERSION}' in html
