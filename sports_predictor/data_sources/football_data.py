from __future__ import annotations
from pathlib import Path
import io, re
import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from .provenance import DataManifest

SEASON_RE = re.compile(r"^\d{4}-\d{2}$")
LEAGUE_RE = re.compile(r"^[A-Z0-9]{1,6}$")
MAX_DOWNLOAD_BYTES = 25 * 1024 * 1024


class FootballDataSource:
    """Downloader/normalizer for football-data.co.uk CSV files.

    The normalized output contains only fields known before or at full time.
    Closing odds are retained for evaluation, but never silently inserted into
    a no-market model.
    """
    BASE = "https://www.football-data.co.uk/mmz4281/{season_code}/{league}.csv"

    def __init__(self, cache_dir: str | Path = "data/raw/football"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        retry = Retry(total=4, backoff_factor=0.8, status_forcelist=(429, 500, 502, 503, 504))
        self.session = requests.Session()
        self.session.mount("https://", HTTPAdapter(max_retries=retry))
        self.session.headers["User-Agent"] = "sports-prediction-v2/0.2.1"

    @staticmethod
    def season_code(season: str) -> str:
        if not SEASON_RE.match(season):
            raise ValueError("Season must look like 2023-24")
        return season[2:4] + season[-2:]

    def fetch(self, season: str, league: str = "E0", force: bool = False) -> tuple[pd.DataFrame, DataManifest]:
        code = self.season_code(season)
        league = str(league).upper()
        if not LEAGUE_RE.fullmatch(league):
            raise ValueError("League code must contain only 1-6 uppercase letters or digits")
        url = self.BASE.format(season_code=code, league=league)
        raw = self.cache_dir / f"{season}_{league}.csv"
        if force or not raw.exists():
            r = self.session.get(url, timeout=45)
            r.raise_for_status()
            payload = r.content
            if len(payload) > MAX_DOWNLOAD_BYTES:
                raise ValueError("Football source file exceeds download size limit")
            temporary = raw.with_suffix(raw.suffix + ".tmp")
            temporary.write_bytes(payload)
            temporary.replace(raw)
        try:
            src = pd.read_csv(raw, encoding="utf-8")
        except UnicodeDecodeError:
            src = pd.read_csv(raw, encoding="cp1252")
        out = self.normalize(src, league=league, season=season)
        manifest = DataManifest.from_file(
            sport="football", source_name="Football-Data.co.uk", source_url=url,
            local_path=raw, rows=len(out),
            license_note="Free historical CSV access; verify Football-Data terms and attribution before redistribution/commercial use.")
        manifest.write(raw.with_suffix(".manifest.json"))
        return out, manifest

    @staticmethod
    def normalize(src: pd.DataFrame, *, league: str, season: str) -> pd.DataFrame:
        required = {"Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG"}
        missing = required - set(src.columns)
        if missing:
            raise ValueError(f"Football-Data schema missing: {sorted(missing)}")
        home_team = src["HomeTeam"].astype("string").str.strip()
        away_team = src["AwayTeam"].astype("string").str.strip()
        out = pd.DataFrame({
            "date": pd.to_datetime(src["Date"], dayfirst=True, errors="coerce", utc=True),
            "league": league,
            "season": season,
            "home_team": home_team,
            "away_team": away_team,
            "home_goals": pd.to_numeric(src["FTHG"], errors="coerce"),
            "away_goals": pd.to_numeric(src["FTAG"], errors="coerce"),
        })
        # Preserve a compact, explicit odds view for market benchmarking.
        aliases = {
            "market_home_odds": ["AvgCH", "PSCH", "B365CH", "AvgH", "PSH", "B365H"],
            "market_draw_odds": ["AvgCD", "PSCD", "B365CD", "AvgD", "PSD", "B365D"],
            "market_away_odds": ["AvgCA", "PSCA", "B365CA", "AvgA", "PSA", "B365A"],
        }
        selected_sources: dict[str, str | None] = {}
        for target, candidates in aliases.items():
            col = next((c for c in candidates if c in src.columns), None)
            selected_sources[target] = col
            out[target] = pd.to_numeric(src[col], errors="coerce") if col else float("nan")
        out["market_odds_source"] = "/".join(
            selected_sources[k] or "missing" for k in
            ["market_home_odds", "market_draw_odds", "market_away_odds"]
        )
        out = out.dropna(subset=["date", "home_team", "away_team", "home_goals", "away_goals"])
        out = out[(out["home_team"] != "") & (out["away_team"] != "") &
                  (out["home_team"] != out["away_team"])]
        out = out[(out["home_goals"] >= 0) & (out["away_goals"] >= 0)]
        return (out.drop_duplicates(["date", "league", "home_team", "away_team"], keep="last")
                   .sort_values("date", kind="stable").reset_index(drop=True))

    def fetch_many(self, seasons: list[str], leagues: list[str]) -> tuple[pd.DataFrame, list[DataManifest]]:
        frames, manifests = [], []
        for season in seasons:
            for league in leagues:
                frame, manifest = self.fetch(season, league)
                frames.append(frame); manifests.append(manifest)
        if not frames:
            raise ValueError("No football source requested")
        return pd.concat(frames, ignore_index=True).sort_values("date").reset_index(drop=True), manifests
