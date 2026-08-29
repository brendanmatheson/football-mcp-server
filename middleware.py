"""
middleware.py — Story 4.2: basic auth and rate limiting for the public
deployment.

Raw ASGI middleware rather than FastMCP's full OAuth providers — those are
built for real third-party auth flows (Auth0, WorkOS, GitHub, etc.), which
is overkill for gating a single-server demo. A shared API key plus a
per-IP rate limit is what the story actually calls for.
"""

from __future__ import annotations
import os
import time
from collections import defaultdict, deque


class APIKeyAuthMiddleware:
    """Requires a matching X-API-Key header on every request.

    Reads the expected key from the FOOTBALL_MCP_API_KEY environment
    variable at startup. If that variable is unset, auth is skipped
    entirely — convenient for local development, but make sure it's set
    in any real deployment.
    """

    def __init__(self, app):
        self.app = app
        self.expected_key = os.environ.get("FOOTBALL_MCP_API_KEY")

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not self.expected_key:
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))
        provided = headers.get(b"x-api-key", b"").decode()
        if provided != self.expected_key:
            await send({
                "type": "http.response.start",
                "status": 401,
                "headers": [(b"content-type", b"application/json")],
            })
            await send({
                "type": "http.response.body",
                "body": b'{"error": "invalid or missing X-API-Key header"}',
            })
            return

        await self.app(scope, receive, send)


class RateLimitMiddleware:
    """Simple in-memory sliding-window rate limiter, per client IP.

    Fine for a single-instance demo deployment. Would need a shared store
    (e.g. Redis) instead of in-process memory if this ever runs behind a
    load balancer with more than one instance.
    """

    def __init__(self, app, max_requests: int = 30, window_seconds: int = 60):
        self.app = app
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._hits: dict[str, deque] = defaultdict(deque)

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        client = scope.get("client")
        ip = client[0] if client else "unknown"
        now = time.time()
        hits = self._hits[ip]
        while hits and now - hits[0] > self.window_seconds:
            hits.popleft()

        if len(hits) >= self.max_requests:
            await send({
                "type": "http.response.start",
                "status": 429,
                "headers": [(b"content-type", b"application/json")],
            })
            await send({
                "type": "http.response.body",
                "body": b'{"error": "rate limit exceeded, try again shortly"}',
            })
            return

        hits.append(now)
        await self.app(scope, receive, send)