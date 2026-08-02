from __future__ import annotations

import re
import unicodedata


_FOOTBALL_ALIASES = {
    "manchester city": "Man City",
    "man city": "Man City",
    "manchester united": "Man United",
    "man united": "Man United",
    "nottingham forest": "Nott'm Forest",
    "nottm forest": "Nott'm Forest",
    "nott m forest": "Nott'm Forest",
    "tottenham hotspur": "Tottenham",
    "tottenham": "Tottenham",
    "wolverhampton wanderers": "Wolves",
    "wolves": "Wolves",
    "newcastle united": "Newcastle",
    "newcastle": "Newcastle",
    "brighton and hove albion": "Brighton",
    "brighton": "Brighton",
    "west ham united": "West Ham",
    "west ham": "West Ham",
    "sheffield united": "Sheffield United",
    "afc bournemouth": "Bournemouth",
    "bournemouth": "Bournemouth",
    "luton town": "Luton",
    "burnley": "Burnley",
    "arsenal": "Arsenal",
    "aston villa": "Aston Villa",
    "brentford": "Brentford",
    "chelsea": "Chelsea",
    "crystal palace": "Crystal Palace",
    "everton": "Everton",
    "fulham": "Fulham",
    "liverpool": "Liverpool",
}


def normalize_identity(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode("ascii")
    text = text.lower().replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def football_model_name(value: str) -> str:
    normalized = normalize_identity(value)
    return _FOOTBALL_ALIASES.get(normalized, str(value).strip())
