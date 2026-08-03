from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
from typing import Any, Iterable

import pandas as pd
import requests

from .artifacts import write_artifact_manifest
from .football import FootballPredictor


SEASON_SOURCES: dict[str, str] = {
    "2021-22": "https://raw.githubusercontent.com/datasets/football-datasets/main/datasets/premier-league/season-2122.csv",
    "2022-23": "https://raw.githubusercontent.com/datasets/football-datasets/main/datasets/premier-league/season-2223.csv",
    "2023-24": "https://raw.githubusercontent.com/datasets/football-datasets/main/datasets/premier-league/season-2324.csv",
    "2024-25": "https://raw.githubusercontent.com/datasets/football-datasets/main/datasets/premier-league/season-2425.csv",
    "2025-26": "https://raw.githubusercontent.com/datasets/football-datasets/main/datasets/premier-league/season-2526.csv",
}

TEAM_ALIASES = {
    "Man United": "Man United",
    "Manchester United": "Man United",
    "Man City": "Man City",
    "Manchester City": "Man City",
    "Nott'm Forest": "Nott'm Forest",
    "Nottingham Forest": "Nott'm Forest",
    "Spurs": "Tottenham",
    "Tottenham Hotspur": "Tottenham",
}


@dataclass(frozen=True)
class PromotionPolicy:
    minimum_rows: int = 1500
    minimum_test_rows: int = 250
    maximum_age_days: int = 240
    maximum_ece: float = 0.15
    require_better_than_naive: bool = True


@dataclass(frozen=True)
class PromotionDecision:
    eligible: bool
    checks: dict[str, bool]
    reasons: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download_season(
    season: str,
    target: str | Path,
    *,
    session: requests.Session | None = None,
    timeout_seconds: int = 30,
    maximum_bytes: int = 5_000_000,
) -> Path:
    if season not in SEASON_SOURCES:
        raise ValueError(f"Unsupported Premier League season: {season}")
    destination = Path(target)
    destination.parent.mkdir(parents=True, exist_ok=True)
    client = session or requests.Session()
    response = client.get(SEASON_SOURCES[season], timeout=timeout_seconds, stream=True)
    response.raise_for_status()
    temporary = destination.with_suffix(destination.suffix + ".part")
    total = 0
    with temporary.open("wb") as handle:
        for chunk in response.iter_content(chunk_size=64 * 1024):
            if not chunk:
                continue
            total += len(chunk)
            if total > maximum_bytes:
                temporary.unlink(missing_ok=True)
                raise ValueError("Downloaded football season exceeds the configured size limit")
            handle.write(chunk)
    temporary.replace(destination)
    return destination


def normalize_season_frame(frame: pd.DataFrame, *, season: str, source: str) -> pd.DataFrame:
    required = {"Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"Missing source columns for {season}: {sorted(missing)}")
    normalized = pd.DataFrame({
        "date": pd.to_datetime(frame["Date"], utc=True, errors="coerce"),
        "league": "E0",
        "home_team": frame["HomeTeam"].astype(str).str.strip().replace(TEAM_ALIASES),
        "away_team": frame["AwayTeam"].astype(str).str.strip().replace(TEAM_ALIASES),
        "home_goals": pd.to_numeric(frame["FTHG"], errors="coerce"),
        "away_goals": pd.to_numeric(frame["FTAG"], errors="coerce"),
        "season": str(season),
        "source": str(source),
    })
    normalized = normalized.dropna(subset=["date", "home_team", "away_team", "home_goals", "away_goals"])
    normalized["home_goals"] = normalized["home_goals"].astype(int)
    normalized["away_goals"] = normalized["away_goals"].astype(int)
    normalized = normalized[
        (normalized["home_team"] != "")
        & (normalized["away_team"] != "")
        & (normalized["home_team"] != normalized["away_team"])
        & (normalized["home_goals"] >= 0)
        & (normalized["away_goals"] >= 0)
    ]
    normalized = normalized.drop_duplicates(subset=["date", "home_team", "away_team"], keep="last")
    return normalized.sort_values(["date", "home_team", "away_team"]).reset_index(drop=True)


def build_multiseason_dataset(paths: Iterable[str | Path]) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for raw_path in paths:
        path = Path(raw_path)
        season = path.stem.replace("epl_", "").replace("_", "-")
        frame = pd.read_csv(path)
        frames.append(normalize_season_frame(frame, season=season, source=path.name))
    if not frames:
        raise ValueError("At least one season file is required")
    combined = pd.concat(frames, ignore_index=True)
    combined = combined.drop_duplicates(subset=["date", "home_team", "away_team"], keep="last")
    combined = combined.sort_values(["date", "home_team", "away_team"]).reset_index(drop=True)
    if combined["date"].nunique() < 100:
        raise ValueError("Fresh football dataset has too few distinct timestamps")
    return combined


def promotion_decision(
    *,
    dataset: pd.DataFrame,
    evaluation: dict[str, Any],
    as_of: Any | None = None,
    policy: PromotionPolicy | None = None,
) -> PromotionDecision:
    rules = policy or PromotionPolicy()
    metrics = dict(evaluation.get("metrics") or evaluation)
    n_test = int(evaluation.get("n_test", metrics.get("n_test", 0)) or 0)
    cutoff = pd.to_datetime(dataset["date"], utc=True, errors="coerce").max()
    reference = pd.to_datetime(as_of or datetime.now(timezone.utc), utc=True)
    age_days = int(max(0, (reference - cutoff).total_seconds() // 86400)) if not pd.isna(cutoff) else 999999
    log_loss = float(metrics.get("log_loss", float("inf")))
    naive = float(metrics.get("naive_log_loss", float("inf")))
    ece = float(metrics.get("ece", float("inf")))
    checks = {
        "minimum_rows": len(dataset) >= rules.minimum_rows,
        "minimum_test_rows": n_test >= rules.minimum_test_rows,
        "fresh_cutoff": age_days <= rules.maximum_age_days,
        "finite_log_loss": pd.notna(log_loss) and log_loss < float("inf"),
        "better_than_naive": (log_loss < naive) if rules.require_better_than_naive else True,
        "calibration": ece <= rules.maximum_ece,
    }
    labels = {
        "minimum_rows": f"moins de {rules.minimum_rows} matchs disponibles",
        "minimum_test_rows": f"moins de {rules.minimum_test_rows} matchs dans le test chronologique",
        "fresh_cutoff": f"données trop anciennes ({age_days} jours)",
        "finite_log_loss": "log-loss invalide",
        "better_than_naive": "le candidat ne bat pas la baseline naïve",
        "calibration": f"ECE supérieure à {rules.maximum_ece:.2f}",
    }
    reasons = [labels[name] for name, passed in checks.items() if not passed]
    return PromotionDecision(eligible=all(checks.values()), checks=checks, reasons=reasons)


def rebuild_candidate(
    *,
    dataset: pd.DataFrame,
    artifacts_dir: str | Path,
    data_output: str | Path,
    promote: bool = False,
    policy: PromotionPolicy | None = None,
    as_of: Any | None = None,
) -> dict[str, Any]:
    out = Path(artifacts_dir)
    out.mkdir(parents=True, exist_ok=True)
    data_path = Path(data_output)
    data_path.parent.mkdir(parents=True, exist_ok=True)
    export = dataset.copy()
    export["date"] = pd.to_datetime(export["date"], utc=True).dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    export.to_csv(data_path, index=False)

    model = FootballPredictor()
    evaluation_obj = model.fit(dataset)
    candidate_path = out / "football_model_candidate.joblib"
    model.save(candidate_path)
    evaluation = evaluation_obj.to_dict()
    decision = promotion_decision(dataset=dataset, evaluation=evaluation, as_of=as_of, policy=policy)
    report = {
        "version": "3.9.0",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "dataset": {
            "path": str(data_path),
            "sha256": sha256_file(data_path),
            "rows": len(dataset),
            "distinct_timestamps": int(pd.to_datetime(dataset["date"], utc=True).nunique()),
            "first_date": pd.to_datetime(dataset["date"], utc=True).min().isoformat(),
            "last_date": pd.to_datetime(dataset["date"], utc=True).max().isoformat(),
            "seasons": sorted(str(x) for x in dataset.get("season", pd.Series(dtype=str)).dropna().unique()),
        },
        "evaluation": evaluation,
        "promotion": decision.to_dict(),
        "candidate_artifact": candidate_path.name,
        "promoted": False,
    }
    if promote and decision.eligible:
        active_model = out / "football_model.joblib"
        shutil.copy2(candidate_path, active_model)
        active_data = data_path.parent / "football_active.csv"
        shutil.copy2(data_path, active_data)
        metrics_path = out / "metrics.json"
        previous = json.loads(metrics_path.read_text(encoding="utf-8")) if metrics_path.exists() else {}
        previous.update({
            "mode": "fresh-multiseason-football",
            "football": evaluation,
            "fresh_rebuild": report["dataset"],
            "warning": "Candidate promoted only after chronological checks; market validation remains required.",
        })
        metrics_path.write_text(json.dumps(previous, indent=2, ensure_ascii=False), encoding="utf-8")
        tennis_model = out / "tennis_model.joblib"
        manifest_files = [active_model, metrics_path]
        if tennis_model.exists():
            manifest_files.append(tennis_model)
        write_artifact_manifest(manifest_files, out / "artifact_manifest.json")
        report["promoted"] = True
        report["active_data"] = str(active_data)
    report_path = out / "fresh_rebuild_report.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return report
