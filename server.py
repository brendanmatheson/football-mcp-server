"""
server.py — Football Intelligence & Optimization Server (FastMCP).

Run locally with the MCP Inspector:
    uv run fastmcp dev inspector server.py

Or directly:
    uv run python server.py

Tools:
    get_players             — browse/filter the raw player pool
    compare_players         — side-by-side comparison of 2-5 players, with xG
    find_value_picks        — ranked points-per-million shortlist, with xG
    get_fixture_difficulty  — FPL's official FDR rating, per team, next N gameweeks
    optimize_fpl_squad      — builds the optimal 15-man squad + starting XI under budget

Prompts (ready-made structured asks for an MCP client to surface directly):
    weekly_transfer_advice  — chains fixtures + value picks + optimizer into transfer advice
    captain_pick_advice     — chains fixtures + form into a captain/vice-captain recommendation
"""

from __future__ import annotations
from fastmcp import FastMCP
from player_pool import get_player_pool
from points_prediction import add_points_prediction
from optimize_squad import optimize_squad as run_squad_optimizer, FORMATIONS
from compare_players import compare_players as run_compare_players
from fixture_difficulty import get_fixture_difficulty as run_fixture_difficulty, summarize_difficulty
from value_picks import find_value_picks as run_find_value_picks
from understat_client import UnderstatDataSource
from xg_enrichment import merge_xg_data

mcp = FastMCP("Football Intelligence & Optimization Server")
_understat = UnderstatDataSource()

# Understat's season format is the year the season STARTED. Try the current
# season first; if it's too early in the year to have data yet, fall back
# to last season rather than failing the whole tool.
CURRENT_SEASON_GUESS = "2026"
FALLBACK_SEASON = "2025"


def _try_enrich_with_xg(df, season: str | None):
    """Returns (possibly-enriched df, an optional note string). Never raises —
    xG context is a nice-to-have, not something that should break a tool
    that otherwise works fine on FPL data alone."""
    seasons_to_try = [season] if season else [CURRENT_SEASON_GUESS, FALLBACK_SEASON]
    for i, s in enumerate(seasons_to_try):
        try:
            understat_df = _understat.get_player_xg_data(season=s)
        except RuntimeError:
            continue
        merged = merge_xg_data(df, understat_df)
        note = None
        if season is None and i > 0:
            note = f"Current season has no xG data yet — showing {s}/{int(s) + 1 - 2000} season instead."
        unmatched = int((merged["xg_match_quality"] == "unmatched").sum())
        if unmatched:
            extra = f"{unmatched} player(s) couldn't be matched to xG data."
            note = f"{note} {extra}" if note else extra
        return merged, note
    return df, "xG data unavailable right now — showing FPL stats only."


@mcp.prompt
def weekly_transfer_advice(budget: float = 100.0, formation: str | None = None) -> str:
    """Ready-made prompt: pulls fixtures, value picks, and an optimized squad,
    then asks for a structured transfer recommendation."""
    formation_note = f" using a {formation} formation" if formation else ""
    return (
        f"I want transfer advice for my Fantasy Premier League squad{formation_note}, "
        f"with a total budget of £{budget}m. Please:\n"
        "1. Check get_fixture_difficulty for the next 5 gameweeks to spot teams with good runs\n"
        "2. Use find_value_picks to identify undervalued players in good form\n"
        "3. Run optimize_fpl_squad to build the best possible squad within budget\n"
        "4. Summarize your top 3 recommended transfers in and out, explaining the "
        "reasoning behind each one, referencing fixture difficulty and value where relevant"
    )


@mcp.prompt
def captain_pick_advice() -> str:
    """Ready-made prompt: gathers fixture difficulty and in-form players to
    recommend a captain and vice-captain for the coming gameweek."""
    return (
        "Help me pick a captain and vice-captain for my Fantasy Premier League "
        "team this gameweek. Please:\n"
        "1. Check get_fixture_difficulty for just the next gameweek\n"
        "2. Use find_value_picks (with a low min_minutes so recent risers aren't "
        "excluded) to see who's in form\n"
        "3. Recommend a captain and vice-captain, favoring players with easy "
        "fixtures and strong recent form/xG over reputation alone"
    )


@mcp.tool()
def find_value_picks(
    position: str | None = None,
    min_minutes: int = 450,
    top_n: int = 10,
    include_xg: bool = True,
    understat_season: str | None = None,
) -> dict:
    """
    Find the best value-for-money players, ranked by points per £m spent
    rather than raw points — surfaces undervalued performers.

    position: one of 'GKP', 'DEF', 'MID', 'FWD' — omit for all positions
    min_minutes: exclude players below this many minutes played (default 450)
    top_n: how many results to return (default 10)
    include_xg: also show xG/xA and over/underperformance vs those numbers
                (default True) — silently skipped if unavailable
    understat_season: e.g. '2025' for the 2025/26 season — omit to auto-try
                       the current season, falling back to last season
    """
    try:
        df = run_find_value_picks(position=position, min_minutes=min_minutes, top_n=top_n)
    except ValueError as e:
        return {"status": "error", "message": str(e)}

    xg_note = None
    if include_xg and not df.empty:
        df, xg_note = _try_enrich_with_xg(df, understat_season)

    result = {"status": "ok", "players": df.to_dict(orient="records")}
    if xg_note:
        result["xg_note"] = xg_note
    return result


@mcp.tool()
def get_players(position: str | None = None, max_price: float | None = None) -> list[dict]:
    """
    Browse the full current FPL player pool, optionally filtered by position
    and/or max price. Returns players in no particular order — use this to
    look someone up or browse a filtered list. For a ranked "best value"
    shortlist, use find_value_picks instead.

    position: one of 'GKP', 'DEF', 'MID', 'FWD' — omit for all positions
    max_price: maximum price in £m — omit for no cap
    """
    df = get_player_pool(position=position, max_price=max_price)
    return df.to_dict(orient="records")


@mcp.tool()
def compare_players(
    player_ids: list[int],
    include_xg: bool = True,
    understat_season: str | None = None,
) -> dict:
    """
    Compare 2-5 FPL players side by side on price, form, total points,
    minutes, ownership, and (when available) xG/xA underlying numbers.

    player_ids: 2-5 FPL player IDs to compare
    include_xg: also show xG/xA and over/underperformance vs those numbers
                (default True) — silently skipped if unavailable
    understat_season: e.g. '2025' for the 2025/26 season — omit to auto-try
                       the current season, falling back to last season
    """
    try:
        df = run_compare_players(player_ids)
    except ValueError as e:
        return {"status": "error", "message": str(e)}

    xg_note = None
    if include_xg:
        df, xg_note = _try_enrich_with_xg(df, understat_season)

    result = {"status": "ok", "players": df.to_dict(orient="records")}
    if xg_note:
        result["xg_note"] = xg_note
    return result


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
    import os
    from starlette.middleware import Middleware
    from middleware import APIKeyAuthMiddleware, RateLimitMiddleware

    transport = os.environ.get("MCP_TRANSPORT", "stdio")

    if transport == "http":
        # Production/deployment path: bind to all interfaces so the
        # container's port mapping works, read the port from the platform
        # (Railway/Fly both inject PORT), and gate the public endpoint.
        port = int(os.environ.get("PORT", 8000))
        mcp.run(
            transport="http",
            host="0.0.0.0",
            port=port,
            middleware=[
                Middleware(RateLimitMiddleware, max_requests=30, window_seconds=60),
                Middleware(APIKeyAuthMiddleware),
            ],
        )
    else:
        # Local dev path — unchanged from before (stdio, used by the
        # MCP Inspector and Claude Desktop's local config).
        mcp.run()