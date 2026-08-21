"""
points_prediction.py — Story 2.1: points-prediction proxy.

FPL doesn't hand you future points, so this builds a deliberately simple,
explainable estimate rather than a trained model — good enough to drive
the optimizer, and easy to swap for something fancier later without
touching optimize_squad.py at all.

Blends two signals per player:
  - `form`: FPL's own last-30-days points/match average — captures
    current momentum, rotation risk, and recent injuries
  - a shrunk season-long points-per-90 rate — captures underlying quality,
    pulled towards the position average for anyone who hasn't played
    enough minutes to trust their raw rate (a 30-minute cameo brace
    shouldn't make a player look like the season's best signing)
"""

from __future__ import annotations
import pandas as pd


def _weighted_position_avg(df: pd.DataFrame) -> dict[str, float]:
    """Minutes-weighted average points-per-90 for each position — the
    shrinkage prior for players who haven't played much."""
    played = df[df["minutes"] > 0]
    avgs: dict[str, float] = {}
    for pos, group in played.groupby("position"):
        total_minutes = group["minutes"].sum()
        weighted_points = (group["points_per_90"] * group["minutes"]).sum()
        avgs[pos] = weighted_points / total_minutes if total_minutes > 0 else 0.0
    return avgs


def add_points_prediction(
    players: pd.DataFrame,
    form_weight: float = 0.6,
    shrinkage_minutes: float = 450,
) -> pd.DataFrame:
    """
    Adds a `predicted_points` column: expected points for a player's next
    appearance.

    form_weight: how much recent form counts vs. the season-long rate
                 (0.6 leans toward "what have you done lately")
    shrinkage_minutes: the "pseudo-minutes" of position-average data a
                 player's own rate is blended against. Larger = more
                 caution around small samples. 450 = ~5 full matches.
    """
    df = players.copy()
    df["points_per_90"] = df.apply(
        lambda r: (r["total_points"] / (r["minutes"] / 90)) if r["minutes"] > 0 else 0.0,
        axis=1,
    )

    position_avg_p90 = _weighted_position_avg(df)
    prior = df["position"].map(position_avg_p90).fillna(0.0)

    # Empirical-Bayes-style shrinkage: more minutes played -> trust the
    # player's own rate more; fewer minutes -> lean on the position average.
    shrink = df["minutes"] / (df["minutes"] + shrinkage_minutes)
    shrunk_p90 = shrink * df["points_per_90"] + (1 - shrink) * prior

    # Convert the per-90 rate into a per-appearance expectation, assuming a
    # ~75-minute average appearance (a reasonable default blending starters
    # and substitutes across the whole player pool).
    season_estimate = shrunk_p90 * (75 / 90)

    df["predicted_points"] = (form_weight * df["form"] + (1 - form_weight) * season_estimate).round(2)
    return df.drop(columns=["points_per_90"])
