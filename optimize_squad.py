"""
optimize_squad.py — Story 2.2: PuLP-based FPL squad optimizer.

Given a player pool (from Phase 1's get_player_pool), this selects:
  - A valid 15-man squad (2 GK / 5 DEF / 5 MID / 3 FWD) under budget
    and the max-3-players-per-club rule
  - The best starting XI within a chosen (or flexible) formation
  - A captain (2x points) and vice-captain

This is the LP core that story 2.4 wires into the `optimize_squad` MCP tool.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Optional
import pandas as pd
import pulp

SQUAD_QUOTAS = {"GKP": 2, "DEF": 5, "MID": 5, "FWD": 3}

# Common formations as (DEF, MID, FWD) — goalkeeper is always exactly 1.
FORMATIONS = {
    "3-4-3": (3, 4, 3),
    "3-5-2": (3, 5, 2),
    "4-3-3": (4, 3, 3),
    "4-4-2": (4, 4, 2),
    "4-5-1": (4, 5, 1),
    "5-3-2": (5, 3, 2),
    "5-4-1": (5, 4, 1),
}

# If no formation is specified, allow any legal FPL shape.
FLEXIBLE_RANGE = {"DEF": (3, 5), "MID": (2, 5), "FWD": (1, 3)}


@dataclass
class OptimizationResult:
    status: str
    squad: pd.DataFrame = None
    starting_xi: pd.DataFrame = None
    captain_id: Optional[int] = None
    vice_captain_id: Optional[int] = None
    total_cost: float = 0.0
    predicted_points: float = 0.0
    message: str = ""


def optimize_squad(
    players: pd.DataFrame,
    budget: float = 100.0,
    formation: Optional[str] = None,
    must_include: Optional[list[int]] = None,
    exclude: Optional[list[int]] = None,
    bench_weight: float = 0.15,
) -> OptimizationResult:
    """
    players: DataFrame with columns
        id, name, team_id, position ('GKP'/'DEF'/'MID'/'FWD'),
        price (float, £m), predicted_points (float)
    budget: total squad budget in £m (FPL default: 100.0)
    formation: a FORMATIONS key, or None to let the solver pick any legal shape
    must_include / exclude: player ids to force in or out
    bench_weight: how much bench quality counts in the objective
                  (0 = ignore the bench, 1 = value it like a starter)
    """
    must_include = must_include or []
    exclude = exclude or []
    players = players[~players["id"].isin(exclude)].reset_index(drop=True)

    if formation and formation not in FORMATIONS:
        return OptimizationResult(
            status="error",
            message=f"Unknown formation '{formation}'. Choose from {list(FORMATIONS)}.",
        )

    ids = players["id"].tolist()
    idx = players.set_index("id")
    prob = pulp.LpProblem("fpl_squad_optimization", pulp.LpMaximize)

    # Decision variables
    squad = pulp.LpVariable.dicts("squad", ids, cat="Binary")
    lineup = pulp.LpVariable.dicts("lineup", ids, cat="Binary")
    captain = pulp.LpVariable.dicts("captain", ids, cat="Binary")

    # --- Squad constraints ---------------------------------------------
    prob += pulp.lpSum(squad[i] for i in ids) == 15

    for pos, quota in SQUAD_QUOTAS.items():
        pos_ids = idx[idx["position"] == pos].index.tolist()
        prob += pulp.lpSum(squad[i] for i in pos_ids) == quota

    prob += pulp.lpSum(squad[i] * idx.loc[i, "price"] for i in ids) <= budget

    for team_id in idx["team_id"].unique():
        team_ids = idx[idx["team_id"] == team_id].index.tolist()
        prob += pulp.lpSum(squad[i] for i in team_ids) <= 3

    for pid in must_include:
        if pid in squad:
            prob += squad[pid] == 1

    # --- Starting XI constraints ----------------------------------------
    for i in ids:
        prob += lineup[i] <= squad[i]  # can only start if picked in squad
    prob += pulp.lpSum(lineup[i] for i in ids) == 11

    gk_ids = idx[idx["position"] == "GKP"].index.tolist()
    prob += pulp.lpSum(lineup[i] for i in gk_ids) == 1

    if formation:
        def_n, mid_n, fwd_n = FORMATIONS[formation]
        for pos, n in {"DEF": def_n, "MID": mid_n, "FWD": fwd_n}.items():
            pos_ids = idx[idx["position"] == pos].index.tolist()
            prob += pulp.lpSum(lineup[i] for i in pos_ids) == n
    else:
        for pos, (lo, hi) in FLEXIBLE_RANGE.items():
            pos_ids = idx[idx["position"] == pos].index.tolist()
            prob += pulp.lpSum(lineup[i] for i in pos_ids) >= lo
            prob += pulp.lpSum(lineup[i] for i in pos_ids) <= hi

    # --- Captain ----------------------------------------------------------
    for i in ids:
        prob += captain[i] <= lineup[i]  # captain must start
    prob += pulp.lpSum(captain[i] for i in ids) == 1

    # --- Objective ----------------------------------------------------------
    # Starting XI counted at full weight, captain counted again (so effectively
    # doubled), bench counted at a small weight so the solver doesn't dump
    # zero-value players there purely to save budget.
    prob += pulp.lpSum(
        idx.loc[i, "predicted_points"] * lineup[i]
        + idx.loc[i, "predicted_points"] * captain[i]
        + idx.loc[i, "predicted_points"] * bench_weight * (squad[i] - lineup[i])
        for i in ids
    )

    prob.solve(pulp.PULP_CBC_CMD(msg=False))
    status = pulp.LpStatus[prob.status]

    if status != "Optimal":
        return OptimizationResult(
            status="infeasible",
            message=(
                "No valid squad found under these constraints. Common causes: "
                "budget too low, must_include list too large or violates a "
                "position/club quota, or exclude removes a required position."
            ),
        )

    squad_ids = [i for i in ids if squad[i].value() == 1]
    lineup_ids = [i for i in ids if lineup[i].value() == 1]
    captain_id = next(i for i in ids if captain[i].value() == 1)

    lineup_sorted = idx.loc[lineup_ids].sort_values("predicted_points", ascending=False)
    vice_id = next(i for i in lineup_sorted.index if i != captain_id)

    squad_df = idx.loc[squad_ids].reset_index()
    starting_df = idx.loc[lineup_ids].reset_index()

    return OptimizationResult(
        status="optimal",
        squad=squad_df,
        starting_xi=starting_df,
        captain_id=captain_id,
        vice_captain_id=vice_id,
        total_cost=round(squad_df["price"].sum(), 1),
        predicted_points=round(
            starting_df["predicted_points"].sum() + idx.loc[captain_id, "predicted_points"], 1
        ),
    )


if __name__ == "__main__":
    # Small synthetic pool so this runs standalone before Phase 1's live
    # get_player_pool() is wired in. Swap this for real FPL data later.
    import random
    random.seed(7)

    positions = ["GKP"] * 4 + ["DEF"] * 10 + ["MID"] * 10 + ["FWD"] * 8
    rows = []
    for pid, pos in enumerate(positions, start=1):
        rows.append({
            "id": pid,
            "name": f"Player{pid}",
            "team_id": random.randint(1, 6),
            "position": pos,
            "price": round(random.uniform(4.0, 12.5), 1),
            "predicted_points": round(random.uniform(1.0, 9.0), 1),
        })
    sample_players = pd.DataFrame(rows)

    result = optimize_squad(sample_players, budget=100.0, formation="3-4-3")

    if result.status != "optimal":
        print(result.message)
    else:
        print(f"Total cost: £{result.total_cost}m")
        print(f"Projected points (starting XI + captain bonus): {result.predicted_points}")
        cap_name = sample_players.loc[sample_players.id == result.captain_id, "name"].values[0]
        vc_name = sample_players.loc[sample_players.id == result.vice_captain_id, "name"].values[0]
        print(f"Captain: {cap_name}")
        print(f"Vice-captain: {vc_name}")
        print("\nStarting XI:")
        print(
            result.starting_xi[["name", "position", "price", "predicted_points"]]
            .sort_values("position")
            .to_string(index=False)
        )
