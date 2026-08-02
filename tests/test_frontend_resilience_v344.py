from pathlib import Path


def test_frontend_has_null_safe_dom_selector() -> None:
    source = Path("static/app.js").read_text(encoding="utf-8")
    assert "document.querySelector(s) || nullElement(s)" in source
    assert "Élément d’interface absent" in source


def test_frontend_cache_bust_matches_release() -> None:
    html = Path("static/index.html").read_text(encoding="utf-8")
    assert "/static/app.js?v=3.5.0" in html


def test_workflow_deploys_code_even_when_generated_artifacts_are_unchanged() -> None:
    source = Path(".github/workflows/rebuild-fresh-football.yml").read_text(encoding="utf-8")
    assert "Deploy current code and model to Railway" in source
    deploy = source.split("- name: Deploy current code and model to Railway", 1)[1]
    header = deploy.split("env:", 1)[0]
    assert "steps.generated_commit.outputs.changed" not in header
    assert "steps.railway_deploy.outputs.enabled == 'true'" in header
