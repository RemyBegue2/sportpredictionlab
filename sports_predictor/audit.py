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
        "# Audit multi-rôles — Sports Prediction Lab V2.1",
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
