"""
compare_players.py — Story 1.4: side-by-side player comparison.
"""

from __future__ import annotations
import pandas as pd
from player_pool import load_player_pool
from fpl_client import FPLClient

COMPARISON_COLUMNS = [
    "id", "name", "team_name", "position", "price", "form",
    "total_points", "minutes", "selected_by_percent",
]


def compare_players(player_ids: list[int], client: FPLClient | None = None) -> pd.DataFrame:
    """
    player_ids: 2-5 FPL player IDs to compare side by side.
    Raises ValueError for an out-of-range count or an unknown id, so callers
    (e.g. the MCP tool wrapper) can turn that into a clean error response.
    """
    if not (2 <= len(player_ids) <= 5):
        raise ValueError(f"compare_players takes 2-5 player IDs, got {len(player_ids)}")

    pool = load_player_pool(client)
    missing = set(player_ids) - set(pool["id"])
    if missing:
        raise ValueError(f"Unknown player id(s): {sorted(missing)}")

    df = pool[pool["id"].isin(player_ids)][COMPARISON_COLUMNS].copy()

    # Preserve the order the caller asked for, not whatever order the pool happens to be in
    order = {pid: i for i, pid in enumerate(player_ids)}
    df["_order"] = df["id"].map(order)
    return df.sort_values("_order").drop(columns="_order").reset_index(drop=True)
