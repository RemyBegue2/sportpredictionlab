from __future__ import annotations
from pathlib import Path
import numpy as np
import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from .provenance import DataManifest


MAX_DOWNLOAD_BYTES = 50 * 1024 * 1024


class TennisArchiveSource:
    """ATP match archive adapter.

    Default URL points to a maintained archive fork. Its data is suitable for
    research/non-commercial prototypes; production users must secure rights.
    """
    URL = "https://raw.githubusercontent.com/Kadantte/tennis_atp/master/atp_matches_{year}.csv"

    def __init__(self, cache_dir: str | Path = "data/raw/tennis"):
        self.cache_dir = Path(cache_dir); self.cache_dir.mkdir(parents=True, exist_ok=True)
        retry = Retry(total=4, backoff_factor=0.8, status_forcelist=(429, 500, 502, 503, 504))
        self.session = requests.Session(); self.session.mount("https://", HTTPAdapter(max_retries=retry))
        self.session.headers["User-Agent"] = "sports-prediction-v2/0.2.1"

    def fetch(self, year: int, force: bool = False) -> tuple[pd.DataFrame, DataManifest]:
        if not 1968 <= int(year) <= 2100:
            raise ValueError("Unexpected ATP year")
        url = self.URL.format(year=int(year))
        raw = self.cache_dir / f"atp_matches_{year}.csv"
        if force or not raw.exists():
            r = self.session.get(url, timeout=60)
            r.raise_for_status()
            payload = r.content
            if len(payload) > MAX_DOWNLOAD_BYTES:
                raise ValueError("Tennis source file exceeds download size limit")
            temporary = raw.with_suffix(raw.suffix + ".tmp")
            temporary.write_bytes(payload)
            temporary.replace(raw)
        src = pd.read_csv(raw, low_memory=False)
        out = self.normalize(src)
        manifest = DataManifest.from_file(
            sport="tennis", source_name="ATP archive (Kadantte/tennis_atp)", source_url=url,
            local_path=raw, rows=len(out),
            license_note="Archive states CC BY-NC-SA / non-commercial constraints; obtain permission for commercial deployment.")
        manifest.write(raw.with_suffix(".manifest.json"))
        return out, manifest

    @staticmethod
    def normalize(src: pd.DataFrame, *, include_retirements: bool = False) -> pd.DataFrame:
        required = {"tourney_date", "surface", "tourney_level", "winner_name", "loser_name"}
        missing = required - set(src.columns)
        if missing:
            raise ValueError(f"Tennis schema missing: {sorted(missing)}")
        date = pd.to_datetime(src["tourney_date"].astype("Int64").astype(str), format="%Y%m%d", errors="coerce", utc=True)
        winner = src["winner_name"].astype("string").str.strip()
        loser = src["loser_name"].astype("string").str.strip()
        score = src.get("score", pd.Series("", index=src.index)).astype("string").fillna("").str.upper()
        status = np.where(score.str.contains(r"\bW/O\b|WALKOVER", regex=True), "walkover",
                 np.where(score.str.contains(r"\bRET\b|RETIRED", regex=True), "retirement",
                 np.where(score.str.contains(r"\bDEF\b", regex=True), "default", "completed")))
        def column(name: str, default=np.nan) -> pd.Series:
            return src[name] if name in src.columns else pd.Series(default, index=src.index)

        out = pd.DataFrame({
            "date": date,
            "tour": "ATP",
            "surface": src["surface"].fillna("unknown").astype(str).str.lower().str.strip(),
            "tournament_level": src["tourney_level"].fillna("A").astype(str),
            "tournament": column("tourney_name", "Unknown"),
            "round": column("round", "Unknown"),
            "best_of": pd.to_numeric(column("best_of", 3), errors="coerce").fillna(3).astype(int),
            "winner_name": winner,
            "loser_name": loser,
            "winner_rank": pd.to_numeric(column("winner_rank"), errors="coerce"),
            "loser_rank": pd.to_numeric(column("loser_rank"), errors="coerce"),
            "winner_rank_points": pd.to_numeric(column("winner_rank_points"), errors="coerce"),
            "loser_rank_points": pd.to_numeric(column("loser_rank_points"), errors="coerce"),
            "score": score,
            "match_status": status,
            # Post-match serve fields are retained only for explicitly lagged future features.
            "winner_ace": pd.to_numeric(column("w_ace"), errors="coerce"),
            "loser_ace": pd.to_numeric(column("l_ace"), errors="coerce"),
        })
        out = out.dropna(subset=["date", "winner_name", "loser_name"])
        out = out[(out["winner_name"] != "") & (out["loser_name"] != "") &
                  (out["winner_name"] != out["loser_name"])]
        out = out[~out["match_status"].isin(["walkover", "default"])]
        if not include_retirements:
            out = out[out["match_status"] == "completed"]
        dedupe = ["date", "tournament", "round", "winner_name", "loser_name"]
        return (out.drop_duplicates(dedupe, keep="last")
                   .sort_values("date", kind="stable").reset_index(drop=True))

    def fetch_many(self, years: list[int]) -> tuple[pd.DataFrame, list[DataManifest]]:
        frames, manifests = [], []
        for y in years:
            frame, manifest = self.fetch(y); frames.append(frame); manifests.append(manifest)
        if not frames: raise ValueError("No tennis year requested")
        return pd.concat(frames, ignore_index=True).sort_values("date", kind="stable").reset_index(drop=True), manifests
