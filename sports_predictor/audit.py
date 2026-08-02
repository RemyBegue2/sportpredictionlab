from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd


@dataclass
class AuditFinding:
    role: str
    severity: str
    finding: str
    recommendation: str

    def to_dict(self) -> dict[str, str]:
        return self.__dict__.copy()


def audit_football_input(df: pd.DataFrame) -> list[AuditFinding]:
    findings: list[AuditFinding] = []
    required = {"date", "league", "home_team", "away_team", "home_goals", "away_goals"}
    missing = required - set(df.columns)
    if missing:
        return [AuditFinding("Data engineer", "critical", f"Colonnes absentes: {sorted(missing)}", "Bloquer l'entraînement.")]
    if df.duplicated(["date", "league", "home_team", "away_team"]).any():
        findings.append(AuditFinding("Data engineer", "high", "Matchs dupliqués détectés.", "Dédupliquer avant toute mise à jour Elo."))
    if (df["home_goals"] < 0).any() or (df["away_goals"] < 0).any():
        findings.append(AuditFinding("Data quality analyst", "critical", "Buts négatifs détectés.", "Rejeter les lignes invalides."))
    same_timestamp = pd.to_datetime(df["date"], utc=True, errors="coerce").duplicated(keep=False).mean()
    if same_timestamp > 0:
        findings.append(AuditFinding(
            "Auditeur anti-fuite", "high",
            f"{same_timestamp:.1%} des lignes partagent un timestamp.",
            "Prédire tout le lot avant d'appliquer ses résultats.",
        ))
    counts = pd.concat([df["home_team"], df["away_team"]]).value_counts()
    if (counts < 5).any():
        findings.append(AuditFinding("Statisticien", "medium", "Certaines équipes ont moins de cinq observations.", "Utiliser shrinkage, hiérarchie ou abstention."))
    findings.append(AuditFinding("Risk manager", "high", "Une bonne log-loss ne prouve pas une rentabilité.", "Garder cotes, coûts et staking dans une couche séparée."))
    return findings


def audit_tennis_input(df: pd.DataFrame) -> list[AuditFinding]:
    findings: list[AuditFinding] = []
    required = {"date", "surface", "tournament_level", "winner_name", "loser_name"}
    missing = required - set(df.columns)
    if missing:
        return [AuditFinding("Data engineer", "critical", f"Colonnes absentes: {sorted(missing)}", "Bloquer l'entraînement.")]
    if df.duplicated(["date", "winner_name", "loser_name"]).any():
        findings.append(AuditFinding("Data engineer", "high", "Matchs tennis potentiellement dupliqués.", "Ajouter tournoi/round à la clé et dédupliquer."))
    if (df["winner_name"] == df["loser_name"]).any():
        findings.append(AuditFinding("Data quality analyst", "critical", "Gagnant et perdant identiques.", "Rejeter ces lignes."))
    distinct_dates = pd.to_datetime(df["date"], utc=True, errors="coerce").nunique()
    if distinct_dates < 3:
        findings.append(AuditFinding(
            "Statisticien tennis", "critical",
            f"Seulement {distinct_dates} timestamps distincts.",
            "Ne publier aucune calibration; servir une baseline transparente ou s'abstenir.",
        ))
    findings.append(AuditFinding("Fairness auditor", "info", "La symétrie d'ordre doit rester exacte.", "Conserver augmentation, inférence symétrique et test unitaire."))
    findings.append(AuditFinding("Juriste données", "critical", "La source ATP impose des restrictions non commerciales.", "Obtenir des droits avant usage commercial."))
    return findings


def model_card(
    football_metrics: dict[str, Any],
    tennis_metrics: dict[str, Any],
    football_findings: list[AuditFinding],
    tennis_findings: list[AuditFinding],
) -> str:
    lines = [
        "# Audit multi-rôles — Sports Prediction Lab",
        "",
        "Prototype de recherche. Aucun gain ou usage financier n'est validé.",
        "",
        "## Football",
    ]
    for key, value in football_metrics.items():
        lines.append(f"- **{key}**: {value:.6f}" if isinstance(value, float) else f"- **{key}**: {value}")
    lines += ["", "## Tennis"]
    for key, value in tennis_metrics.items():
        lines.append(f"- **{key}**: {value:.6f}" if isinstance(value, float) else f"- **{key}**: {value}")
    lines += ["", "## Findings"]
    for finding in football_findings + tennis_findings:
        lines.append(f"- **{finding.role} — {finding.severity}** : {finding.finding} {finding.recommendation}")
    return "\n".join(lines)


def audit_shadow_predictions(rows: pd.DataFrame | list[dict[str, Any]], *, max_model_age_days: int = 365) -> list[AuditFinding]:
    """Audit immutable shadow predictions without mutating or repairing them."""
    df = rows.copy() if isinstance(rows, pd.DataFrame) else pd.DataFrame(rows)
    if df.empty:
        return [AuditFinding(
            "Statisticien", "info", "Aucune prédiction shadow disponible.",
            "Laisser le verdict non évaluable jusqu'à l'arrivée de résultats pré-match.",
        )]
    required = {
        "provider_event_id", "model_id", "model_version", "horizon",
        "prediction_created_at", "commence_time", "temporal_valid", "decision",
    }
    missing = required - set(df.columns)
    if missing:
        return [AuditFinding(
            "Data engineer", "critical", f"Champs shadow absents: {sorted(missing)}",
            "Bloquer l'évaluation et corriger le schéma de persistance.",
        )]

    findings: list[AuditFinding] = []
    duplicate_key = ["provider_event_id", "model_id", "model_version", "horizon"]
    duplicates = int(df.duplicated(duplicate_key, keep=False).sum())
    if duplicates:
        findings.append(AuditFinding(
            "Statisticien", "high", f"{duplicates} observations dupliquent un même événement/modèle/horizon.",
            "Conserver une observation unique par jalon pour éviter une pseudo-réplication.",
        ))

    created = pd.to_datetime(df["prediction_created_at"], utc=True, errors="coerce")
    commence = pd.to_datetime(df["commence_time"], utc=True, errors="coerce")
    invalid_order = int(((created >= commence) | created.isna() | commence.isna()).sum())
    declared_invalid = int((~df["temporal_valid"].fillna(False).astype(bool)).sum())
    if invalid_order or declared_invalid:
        findings.append(AuditFinding(
            "Auditeur anti-fuite", "critical",
            f"{max(invalid_order, declared_invalid)} prédictions violent ou déclarent invalide l'ordre temporel.",
            "Exclure ces lignes de toutes les métriques et conserver leur trace en quarantaine.",
        ))

    candidate = df["decision"].astype(str).eq("candidat recherche")
    if "market_analysis" in df.columns:
        missing_market = int((candidate & df["market_analysis"].isna()).sum())
        if missing_market:
            findings.append(AuditFinding(
                "Trader de cotes", "critical", f"{missing_market} candidats n'ont aucun marché horodaté.",
                "Interdire le statut candidat sans marché complet et heure de cote.",
            ))

    if "data_cutoff" in df.columns:
        cutoff = pd.to_datetime(df["data_cutoff"], utc=True, errors="coerce")
        ages = (commence - cutoff).dt.total_seconds() / 86400.0
        stale = int((ages > max_model_age_days).fillna(True).sum())
        if stale:
            findings.append(AuditFinding(
                "Ingénieur ML", "high", f"{stale} prédictions utilisent un modèle au-delà du seuil de fraîcheur.",
                "Conserver ces lignes pour observation, mais bloquer toute sélection opérationnelle.",
            ))

    if not findings:
        findings.append(AuditFinding(
            "QA", "info", "Le lot shadow respecte les contrôles structurels et temporels de base.",
            "Poursuivre le suivi de la calibration, des résultats et de la closing line.",
        ))
    return findings
