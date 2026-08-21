"""
server.py — Story 1.1: FastMCP scaffolding and entrypoint.

Run locally with the MCP Inspector:
    mcp dev server.py

Or directly:
    python server.py
"""

from __future__ import annotations
from fastmcp import FastMCP
from player_pool import get_player_pool
from points_prediction import add_points_prediction
from optimize_squad import optimize_squad as run_squad_optimizer, FORMATIONS
from compare_players import compare_players as run_compare_players
from fixture_difficulty import get_fixture_difficulty as run_fixture_difficulty, summarize_difficulty

mcp = FastMCP("Football Intelligence & Optimization Server")


@mcp.tool()
def get_players(position: str | None = None, max_price: float | None = None) -> list[dict]:
    """
    Get current FPL players, optionally filtered by position and/or max price.

    position: one of 'GKP', 'DEF', 'MID', 'FWD' — omit for all positions
    max_price: maximum price in £m — omit for no cap
    """
    df = get_player_pool(position=position, max_price=max_price)
    return df.to_dict(orient="records")


@mcp.tool()
def compare_players(player_ids: list[int]) -> dict:
    """
    Compare 2-5 FPL players side by side on price, form, total points,
    minutes, and ownership.

    player_ids: 2-5 FPL player IDs to compare
    """
    try:
        df = run_compare_players(player_ids)
    except ValueError as e:
        return {"status": "error", "message": str(e)}
    return {"status": "ok", "players": df.to_dict(orient="records")}


@mcp.tool()
def get_fixture_difficulty(next_n_gameweeks: int = 5, team_id: int | None = None) -> dict:
    """
    Get fixture difficulty (FPL's own 1-5 FDR rating) for upcoming gameweeks,
    plus a per-team average — useful for spotting good/bad transfer windows.

    next_n_gameweeks: how many upcoming gameweeks to look at (default 5)
    team_id: restrict to one team — omit for all teams
    """
    try:
        fixtures_df = run_fixture_difficulty(next_n_gameweeks=next_n_gameweeks, team_id=team_id)
    except ValueError as e:
        return {"status": "error", "message": str(e)}

    summary_df = summarize_difficulty(fixtures_df)
    return {
        "status": "ok",
        "fixtures": fixtures_df.to_dict(orient="records"),
        "team_summary": summary_df.to_dict(orient="records"),
    }


@mcp.tool()
def optimize_fpl_squad(
    budget: float = 100.0,
    formation: str | None = None,
    must_include: list[int] | None = None,
    exclude: list[int] | None = None,
) -> dict:
    """
    Build the optimal FPL squad and starting XI under a budget and
    formation, using current player data and a points-prediction proxy.

    budget: total squad budget in £m (default 100.0)
    formation: one of '3-4-3', '3-5-2', '4-3-3', '4-4-2', '4-5-1', '5-3-2',
               '5-4-1' — omit to let the solver pick any legal shape
    must_include: player IDs to force into the squad
    exclude: player IDs to leave out entirely
    """
    pool = get_player_pool()
    pool = add_points_prediction(pool)

    result = run_squad_optimizer(
        pool, budget=budget, formation=formation,
        must_include=must_include, exclude=exclude,
    )

    if result.status != "optimal":
        return {"status": result.status, "message": result.message}

    squad = result.squad
    starting_ids = set(result.starting_xi["id"])
    bench = squad[~squad["id"].isin(starting_ids)]

    cols = ["id", "name", "position", "team_name", "price", "predicted_points"]
    return {
        "status": "optimal",
        "total_cost": result.total_cost,
        "predicted_points": result.predicted_points,
        "captain": squad.loc[squad["id"] == result.captain_id, "name"].values[0],
        "vice_captain": squad.loc[squad["id"] == result.vice_captain_id, "name"].values[0],
        "starting_xi": result.starting_xi[cols].to_dict(orient="records"),
        "bench": bench[cols].to_dict(orient="records"),
    }


if __name__ == "__main__":
    mcp.run()
