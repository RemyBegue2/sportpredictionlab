from __future__ import annotations

from pathlib import Path
import re


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
    assert '/static/app.js?v=3.5.0' in html
