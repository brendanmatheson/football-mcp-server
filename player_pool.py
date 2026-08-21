"""
player_pool.py — Story 1.3: turns raw FPL bootstrap data into a clean
DataFrame in the shape optimize_squad.py already expects
(id, name, team_id, position, price, ...).
"""

from __future__ import annotations
import pandas as pd
from fpl_client import FPLClient

POSITION_MAP = {1: "GKP", 2: "DEF", 3: "MID", 4: "FWD"}


def load_player_pool(client: FPLClient | None = None) -> pd.DataFrame:
    client = client or FPLClient()
    data = client.bootstrap_static()

    teams = {t["id"]: t["name"] for t in data["teams"]}
    rows = []
    for p in data["elements"]:
        rows.append({
            "id": p["id"],
            "name": f"{p['first_name']} {p['second_name']}",
            "team_id": p["team"],
            "team_name": teams.get(p["team"], "Unknown"),
            "position": POSITION_MAP.get(p["element_type"], "UNK"),
            "price": p["now_cost"] / 10,  # FPL stores price in tenths of £m
            "form": float(p["form"]) if p["form"] else 0.0,
            "total_points": p["total_points"],
            "minutes": p["minutes"],
            "selected_by_percent": float(p["selected_by_percent"]),
        })
    return pd.DataFrame(rows)


def get_player_pool(
    position: str | None = None,
    max_price: float | None = None,
    client: FPLClient | None = None,
) -> pd.DataFrame:
    """
    position: one of 'GKP', 'DEF', 'MID', 'FWD' — omit for all
    max_price: maximum price in £m — omit for no cap
    """
    df = load_player_pool(client)
    if position:
        df = df[df["position"] == position.upper()]
    if max_price is not None:
        df = df[df["price"] <= max_price]
    return df.reset_index(drop=True)
