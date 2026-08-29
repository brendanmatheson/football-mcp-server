"""
value_picks.py — Story 3.1: value-pick finder.

Ranks players by points-per-million (PPM) rather than raw points — the
classic "who's punching above their price tag" lens. Ties back to this
project's access/equal-opportunity theme: it's explicitly about finding
undervalued performers, not just listing the most expensive stars.
"""

from __future__ import annotations
import pandas as pd
from player_pool import get_player_pool


def find_value_picks(
    position: str | None = None,
    min_minutes: int = 450,
    top_n: int = 10,
    pool: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """
    position: one of 'GKP', 'DEF', 'MID', 'FWD' — omit for all positions
    min_minutes: exclude players below this many minutes played, so a
                 one-goal substitute cameo doesn't top the list on a
                 statistical technicality (default 450 = ~5 full matches)
    top_n: how many results to return
    pool: inject a pre-fetched DataFrame for testing — omit to fetch live
    """
    if min_minutes < 0:
        raise ValueError(f"min_minutes must be >= 0, got {min_minutes}")
    if top_n < 1:
        raise ValueError(f"top_n must be >= 1, got {top_n}")

    df = pool if pool is not None else get_player_pool(position=position)
    if pool is not None and position:
        df = df[df["position"] == position.upper()]

    df = df[df["minutes"] >= min_minutes].copy()
    if df.empty:
        return df.assign(points_per_million=pd.Series(dtype=float))

    df["points_per_million"] = (df["total_points"] / df["price"]).round(2)
    return (
        df.sort_values("points_per_million", ascending=False)
        .head(top_n)
        .reset_index(drop=True)
    )