"""
xg_enrichment.py — Story 3.3: blend xG/xA context into existing tools.

FPL and understat are two independent, unofficial sources with no shared
player ID — so this has to match players by name, and names don't always
match exactly (accents like "Ødegaard" vs "Odegaard", short names vs full
names). This tries an exact match first, then falls back to fuzzy matching
for the rest, and explicitly flags anything it isn't confident about
rather than silently attaching the wrong player's numbers.
"""

from __future__ import annotations
import unicodedata
import difflib
import pandas as pd

FUZZY_MATCH_THRESHOLD = 0.85
XG_COLUMNS = ["xG", "xA", "goals", "assists"]


def _normalize_name(name: str) -> str:
    """Lowercase and strip accents so 'Ødegaard' and 'Odegaard' compare equal."""
    stripped = unicodedata.normalize("NFKD", str(name)).encode("ascii", "ignore").decode()
    return stripped.lower().strip()


def merge_xg_data(players: pd.DataFrame, understat: pd.DataFrame) -> pd.DataFrame:
    """
    players: FPL player pool / comparison frame — must have a 'name' column
    understat: output of UnderstatDataSource.get_player_xg_data — must have
               'name', 'xG', 'xA', 'goals', 'assists'

    Adds: xG, xA, goals_vs_xg (actual minus expected — positive means
    overperforming/lucky, negative means underperforming/due a goal),
    assists_vs_xa, and xg_match_quality ('exact', 'fuzzy', or 'unmatched').
    """
    df = players.copy()
    understat = understat.copy()
    understat["_norm"] = understat["name"].apply(_normalize_name)
    df["_norm"] = df["name"].apply(_normalize_name)

    lookup = understat.set_index("_norm")

    for col in XG_COLUMNS:
        df[col] = pd.NA
    df["xg_match_quality"] = "unmatched"

    def _apply_match(idx, norm_key, quality):
        match = lookup.loc[norm_key]
        if isinstance(match, pd.DataFrame):  # duplicate normalized names — take the first
            match = match.iloc[0]
        for col in XG_COLUMNS:
            df.at[idx, col] = match[col]
        df.at[idx, "xg_match_quality"] = quality

    exact_keys = set(lookup.index)
    remaining_pool = list(exact_keys)

    for idx, row in df.iterrows():
        if row["_norm"] in exact_keys:
            _apply_match(idx, row["_norm"], "exact")
            if row["_norm"] in remaining_pool:
                remaining_pool.remove(row["_norm"])

    for idx, row in df[df["xg_match_quality"] == "unmatched"].iterrows():
        if not remaining_pool:
            break
        close = difflib.get_close_matches(row["_norm"], remaining_pool, n=1, cutoff=FUZZY_MATCH_THRESHOLD)
        if close:
            _apply_match(idx, close[0], "fuzzy")
            remaining_pool.remove(close[0])

    df["goals_vs_xg"] = (pd.to_numeric(df["goals"]) - pd.to_numeric(df["xG"])).round(2)
    df["assists_vs_xa"] = (pd.to_numeric(df["assists"]) - pd.to_numeric(df["xA"])).round(2)

    return df.drop(columns="_norm")