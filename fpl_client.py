"""
fpl_client.py — Story 1.2: resilient wrapper around the public FPL API.

The FPL API is free, unauthenticated, and undocumented-but-stable. This
wrapper adds timeouts, retries, and a simple time-based cache so we don't
hammer it — bootstrap-static only actually changes a handful of times a
day outside of live gameweeks.
"""

from __future__ import annotations
import time
import httpx

BASE_URL = "https://fantasy.premierleague.com/api"
DEFAULT_TIMEOUT = 10.0
CACHE_TTL_SECONDS = 15 * 60  # 15 minutes


class FPLClient:
    def __init__(self, timeout: float = DEFAULT_TIMEOUT, cache_ttl: int = CACHE_TTL_SECONDS):
        self._timeout = timeout
        self._cache_ttl = cache_ttl
        self._cache: dict[str, tuple[float, dict]] = {}

    def _get(self, path: str, retries: int = 2) -> dict:
        cached = self._cache.get(path)
        if cached and (time.time() - cached[0]) < self._cache_ttl:
            return cached[1]

        last_err: Exception | None = None
        for attempt in range(retries + 1):
            try:
                resp = httpx.get(f"{BASE_URL}/{path}", timeout=self._timeout)
                resp.raise_for_status()
                data = resp.json()
                self._cache[path] = (time.time(), data)
                return data
            except (httpx.HTTPError, httpx.TimeoutException) as e:
                last_err = e
                time.sleep(0.5 * (attempt + 1))
        raise RuntimeError(f"FPL API request failed for '{path}' after {retries + 1} attempts: {last_err}")

    def bootstrap_static(self) -> dict:
        """Players, teams, positions, and gameweek metadata — the core reference data."""
        return self._get("bootstrap-static/")

    def fixtures(self, event: int | None = None) -> list[dict]:
        path = "fixtures/" if event is None else f"fixtures/?event={event}"
        return self._get(path)

    def live_gameweek(self, event: int) -> dict:
        """Live points breakdown for every player in a specific gameweek."""
        return self._get(f"event/{event}/live/")
