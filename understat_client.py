"""
understat_client.py — Story 3.2: xG/xA data integration.

Wraps the community `understatapi` package (github.com/collinb9/understatAPI),
which scrapes understat.com. There's no official xG API, so this is
inherently less stable than the FPL client: understat can rate-limit,
change its markup, or — importantly, right now — simply have no data yet
for a season that only just started. All of that is handled explicitly
here rather than left to surface as a raw exception up in an MCP tool.
"""

from __future__ import annotations
import time
import pandas as pd
from understatapi import UnderstatClient

CACHE_TTL_SECONDS = 60 * 60  # 1 hour — season-long stats change slowly

# understat's JSON returns these as strings; cast them to something usable.
NUMERIC_FIELDS = {
    "games": int, "time": int, "goals": int, "assists": int,
    "shots": int, "key_passes": int, "yellow_cards": int, "red_cards": int,
    "npg": int, "xG": float, "xA": float, "npxG": float,
    "xGChain": float, "xGBuildup": float,
}


class UnderstatDataSource:
    def __init__(self, cache_ttl: int = CACHE_TTL_SECONDS):
        self._cache_ttl = cache_ttl
        self._cache: dict[str, tuple[float, list[dict]]] = {}

    def get_player_xg_data(self, season: str, league: str = "EPL") -> pd.DataFrame:
        """
        season: understat's format — the year the season STARTED,
                e.g. '2025' for the 2025/26 season
        league: 'EPL', 'La_liga', 'Bundesliga', 'Serie_A', 'Ligue_1', or 'RFPL'

        Raises RuntimeError with a clear, specific message on any failure —
        a network/scraping error, or (commonly, early in a new season)
        genuinely no data existing yet.
        """
        cache_key = f"{league}:{season}"
        cached = self._cache.get(cache_key)
        if cached and (time.time() - cached[0]) < self._cache_ttl:
            raw = cached[1]
        else:
            try:
                with UnderstatClient() as client:
                    raw = client.league(league=league).get_player_data(season=season)
            except Exception as e:
                raise RuntimeError(
                    f"Couldn't fetch understat data for {league} {season}: {e}. "
                    "This is an unofficial scraped source, not an API — it may be "
                    "rate-limiting, have changed its page structure, or the season "
                    "may simply be too new to have data yet."
                ) from e
            self._cache[cache_key] = (time.time(), raw)

        if not raw:
            raise RuntimeError(
                f"understat returned no player data for {league} {season}. "
                "Most likely the season hasn't generated enough matches yet — "
                "try again in a week or two, or fall back to last season's data."
            )

        df = pd.DataFrame(raw)
        for col, cast in NUMERIC_FIELDS.items():
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(cast)

        return df.rename(columns={
            "player_name": "name",
            "team_title": "team_name",
            "time": "minutes",
        })