"""
fixture_difficulty.py — Story 1.5: fixture difficulty lookup.

FPL's fixtures endpoint already ships an official difficulty rating (FDR,
1-5) for each side of every fixture. This aggregates that into a per-team
view for the next N gameweeks, since that's what's actually useful when
planning transfers — not the raw fixture list.
"""

from __future__ import annotations
import pandas as pd
from fpl_client import FPLClient


def get_fixture_difficulty(
    next_n_gameweeks: int = 5,
    team_id: int | None = None,
    client: FPLClient | None = None,
) -> pd.DataFrame:
    """
    next_n_gameweeks: how many upcoming gameweeks to look at (must be >= 1)
    team_id: restrict to one team's fixtures — omit for all teams
    Raises ValueError for a non-positive next_n_gameweeks.
    """
    if next_n_gameweeks < 1:
        raise ValueError(f"next_n_gameweeks must be >= 1, got {next_n_gameweeks}")

    client = client or FPLClient()
    fixtures = client.fixtures()
    bootstrap = client.bootstrap_static()
    teams = {t["id"]: t["name"] for t in bootstrap["teams"]}

    upcoming = [f for f in fixtures if not f["finished"] and f.get("event") is not None]
    upcoming.sort(key=lambda f: f["event"])

    gameweeks = sorted({f["event"] for f in upcoming})
    cutoff_gws = set(gameweeks[:next_n_gameweeks])

    rows = []
    for f in upcoming:
        if f["event"] not in cutoff_gws:
            continue
        rows.append({
            "gameweek": f["event"], "team_id": f["team_h"],
            "team_name": teams.get(f["team_h"], "Unknown"),
            "opponent": teams.get(f["team_a"], "Unknown"),
            "is_home": True, "difficulty": f["team_h_difficulty"],
        })
        rows.append({
            "gameweek": f["event"], "team_id": f["team_a"],
            "team_name": teams.get(f["team_a"], "Unknown"),
            "opponent": teams.get(f["team_h"], "Unknown"),
            "is_home": False, "difficulty": f["team_a_difficulty"],
        })

    df = pd.DataFrame(rows)
    if team_id is not None:
        df = df[df["team_id"] == team_id]
    return df.sort_values(["team_id", "gameweek"]).reset_index(drop=True)


def summarize_difficulty(df: pd.DataFrame) -> pd.DataFrame:
    """Collapse per-fixture rows into one average-difficulty score per team —
    the useful bit for a quick 'who has the easiest run' ranking."""
    if df.empty:
        return df
    return (
        df.groupby(["team_id", "team_name"])["difficulty"]
        .mean()
        .round(2)
        .reset_index()
        .rename(columns={"difficulty": "avg_difficulty"})
        .sort_values("avg_difficulty")
        .reset_index(drop=True)
    )
