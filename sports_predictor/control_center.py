from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable

STATUS_ORDER = {"ok": 0, "pending": 1, "attention": 2, "blocked": 3}


WORKFLOW_CATALOG: tuple[dict[str, Any], ...] = (
    {
        "id": "deploy-production",
        "name": "Deploy production",
        "file": "deploy-production.yml",
        "purpose": "Tester, déployer les services Railway et vérifier la release réellement servie.",
        "risk": "controlled",
        "confirmation": None,
        "required_configuration": ["RAILWAY_TOKEN", "RAILWAY_PROJECT_ID", "APP_PUBLIC_URL"],
    },
    {
        "id": "verify-production",
        "name": "Verify production",
        "file": "verify-production.yml",
        "purpose": "Comparer version, commit et hash du modèle avec la production sans redéployer.",
        "risk": "read_only",
        "confirmation": None,
        "required_configuration": ["APP_PUBLIC_URL"],
    },
    {
        "id": "generate-handoff",
        "name": "Generate handoff package",
        "file": "generate-handoff.yml",
        "purpose": "Créer un ZIP sans secret à joindre dans une nouvelle conversation.",
        "risk": "read_only",
        "confirmation": None,
        "required_configuration": [],
    },
    {
        "id": "historical-validation",
        "name": "Historical validation sample",
        "file": "historical-validation.yml",
        "purpose": "Planifier ou exécuter un petit lot historique plafonné à 30 événements.",
        "risk": "consumes_api_credits",
        "confirmation": "EXECUTE_SAMPLE",
        "required_configuration": ["THE_ODDS_API_KEY", "DATABASE_URL"],
    },
    {
        "id": "backup-database",
        "name": "Backup and verify database",
        "file": "backup-database.yml",
        "purpose": "Créer une sauvegarde applicative et vérifier sa restauration dans une base temporaire.",
        "risk": "read_only_production",
        "confirmation": None,
        "required_configuration": ["DATABASE_URL", "BACKUP_ENCRYPTION_PASSPHRASE"],
    },
    {
        "id": "rollback-production",
        "name": "Rollback model release",
        "file": "rollback-production.yml",
        "purpose": "Restaurer les artefacts d’un commit Git connu, tester, déployer puis vérifier la production.",
        "risk": "destructive",
        "confirmation": "ROLLBACK",
        "required_configuration": ["RAILWAY_TOKEN", "RAILWAY_PROJECT_ID", "APP_PUBLIC_URL"],
    },
    {
        "id": "rebuild-fresh-football",
        "name": "Rebuild fresh football model",
        "file": "rebuild-fresh-football.yml",
        "purpose": "Télécharger, entraîner, évaluer et promouvoir conditionnellement un candidat frais.",
        "risk": "controlled",
        "confirmation": None,
        "required_configuration": ["RAILWAY_TOKEN", "RAILWAY_PROJECT_ID", "APP_PUBLIC_URL"],
    },
)


def _parse_utc(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _check(
    check_id: str,
    label: str,
    status: str,
    detail: str,
    action: str,
    workflow: str | None = None,
) -> dict[str, Any]:
    if status not in STATUS_ORDER:
        raise ValueError(f"Unsupported control-center status: {status}")
    return {
        "id": check_id,
        "label": label,
        "status": status,
        "detail": detail,
        "action": action,
        "workflow": workflow,
    }


def _overall(checks: Iterable[dict[str, Any]]) -> str:
    return max((str(item["status"]) for item in checks), key=lambda value: STATUS_ORDER[value], default="pending")


def build_control_center(
    *,
    release: dict[str, Any],
    database: dict[str, Any],
    models: list[dict[str, Any]],
    shadow_cycle: dict[str, Any] | None,
    benchmark: dict[str, Any] | None,
    model_decision: dict[str, Any] | None,
    backfills: list[dict[str, Any]],
    now: datetime | None = None,
) -> dict[str, Any]:
    reference = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    checks: list[dict[str, Any]] = []

    app = release.get("app") or {}
    integrity = release.get("integrity") or {}
    release_ok = bool(integrity.get("artifact_integrity_ok")) and app.get("source_commit") not in {None, "", "unknown"}
    checks.append(_check(
        "production-release",
        "Release de production",
        "ok" if release_ok else "blocked",
        (
            f"Version {app.get('version', 'inconnue')} · commit {app.get('source_commit_short', 'inconnu')} · intégrité vérifiée."
            if release_ok else
            "La version, le commit ou l’intégrité des artefacts ne sont pas prouvés."
        ),
        "Lancer la vérification de production." if not release_ok else "Aucune action immédiate.",
        "verify-production" if not release_ok else None,
    ))

    db_connected = bool(database.get("connected"))
    quality_issues = int(database.get("open_data_quality_issues") or 0)
    db_status = "blocked" if not db_connected else ("attention" if quality_issues else "ok")
    checks.append(_check(
        "database",
        "PostgreSQL et qualité des données",
        db_status,
        (
            "Base indisponible."
            if not db_connected else
            f"Base connectée · {database.get('odds_snapshots', 0)} snapshots · {quality_issues} anomalie(s) ouverte(s)."
        ),
        "Vérifier Railway/Postgres." if not db_connected else ("Traiter les anomalies ouvertes." if quality_issues else "Aucune action immédiate."),
        None,
    ))

    football_models = [item for item in models if item.get("sport") == "football"]
    active = [item for item in football_models if item.get("status") == "active"]
    shadow = [item for item in football_models if item.get("status") in {"shadow", "degraded"}]
    model_status = "ok" if len(active) == 1 else ("attention" if shadow else "blocked")
    model_detail = (
        f"Champion actif : {active[0].get('model_id')}@{active[0].get('version')}."
        if len(active) == 1 else
        (f"Aucun champion actif · {len(shadow)} modèle(s) en shadow/degraded." if shadow else "Aucun modèle football exploitable enregistré.")
    )
    checks.append(_check(
        "model-registry",
        "Registre des modèles",
        model_status,
        model_detail,
        "Continuer le shadow et demander une revue humaine avant toute promotion." if not active else "Aucune promotion automatique.",
        "rebuild-fresh-football" if not football_models else None,
    ))

    cycle_finished = _parse_utc((shadow_cycle or {}).get("finished_at") or (shadow_cycle or {}).get("started_at"))
    if shadow_cycle is None:
        cycle_status = "pending"
        cycle_detail = "Aucun cycle shadow enregistré."
        cycle_action = "Vérifier le service Railway shadow-cron."
    else:
        age_hours = (reference - cycle_finished).total_seconds() / 3600 if cycle_finished else None
        failed = str(shadow_cycle.get("status", "")).casefold() not in {"ok", "success", "completed"}
        stale = age_hours is not None and age_hours > 48
        cycle_status = "blocked" if failed else ("attention" if stale else "ok")
        age_text = f"{age_hours:.1f} h" if age_hours is not None else "âge inconnu"
        cycle_detail = f"Dernier cycle : {shadow_cycle.get('status', 'inconnu')} · {age_text}."
        cycle_action = "Contrôler les logs du service shadow-cron." if cycle_status != "ok" else "Aucune action immédiate."
    checks.append(_check("shadow-cron", "Cycle shadow", cycle_status, cycle_detail, cycle_action, None))

    decision = ((model_decision or {}).get("decision") or model_decision or {})
    decision_status = str(decision.get("status") or "not_evaluable")
    if decision_status == "promotion_review":
        evidence_status = "attention"
        evidence_action = "Effectuer une revue humaine des portes de promotion."
    elif decision_status == "no_go":
        evidence_status = "attention"
        evidence_action = "Conserver le champion actuel et analyser les segments faibles."
    elif decision_status == "continue_shadow":
        evidence_status = "pending"
        evidence_action = "Continuer la collecte shadow et historique."
    else:
        evidence_status = "pending"
        evidence_action = "Lancer le petit lot historique contrôlé."
    evaluated = int((benchmark or {}).get("evaluated_rows") or decision.get("historical_predictions") or 0)
    checks.append(_check(
        "evidence",
        "Preuve statistique",
        evidence_status,
        f"Verdict : {decision_status} · {evaluated} observation(s) historiques évaluées.",
        evidence_action,
        "historical-validation" if decision_status in {"not_evaluable", "continue_shadow"} else None,
    ))

    latest_backfill = backfills[0] if backfills else None
    if latest_backfill is None:
        backfill_status = "pending"
        backfill_detail = "Aucun backfill historique enregistré."
        backfill_action = "Planifier le lot de validation plafonné."
    else:
        raw_status = str(latest_backfill.get("status") or "unknown").casefold()
        if raw_status in {"failed", "error", "blocked"}:
            backfill_status = "blocked"
        elif raw_status in {"running", "planned", "pending"}:
            backfill_status = "attention"
        else:
            backfill_status = "ok"
        backfill_detail = (
            f"Dernier backfill : {raw_status} · "
            f"{latest_backfill.get('completed_requests', 0)}/{latest_backfill.get('request_count', 0)} requêtes."
        )
        backfill_action = "Consulter le résumé du workflow historique." if backfill_status != "ok" else "Aucune action immédiate."
    checks.append(_check(
        "historical-backfill",
        "Collecte historique",
        backfill_status,
        backfill_detail,
        backfill_action,
        "historical-validation" if backfill_status != "ok" else None,
    ))

    overall = _overall(checks)
    actionable = [item for item in checks if item["status"] in {"blocked", "attention", "pending"}]
    return {
        "schema_version": "1.0",
        "generated_at_utc": reference.isoformat(),
        "overall_status": overall,
        "summary": {
            "ok": sum(item["status"] == "ok" for item in checks),
            "pending": sum(item["status"] == "pending" for item in checks),
            "attention": sum(item["status"] == "attention" for item in checks),
            "blocked": sum(item["status"] == "blocked" for item in checks),
        },
        "checks": checks,
        "next_actions": [
            {
                "priority": index + 1,
                "label": item["label"],
                "action": item["action"],
                "workflow": item.get("workflow"),
            }
            for index, item in enumerate(sorted(actionable, key=lambda row: STATUS_ORDER[row["status"]], reverse=True)[:5])
        ],
        "workflows": [dict(item) for item in WORKFLOW_CATALOG],
        "local_python_required": False,
        "operation_mode": "github_actions_and_railway",
        "safety": {
            "automatic_model_promotion": False,
            "automatic_bet_placement": False,
            "staking_recommendations": False,
            "secrets_exposed": False,
        },
    }
