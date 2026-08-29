# Football Intelligence & Optimization Server — deployment image

# Platform pinned explicitly: PuLP bundles a CBC solver binary compiled for
# linux/amd64 specifically (confirmed at pulp/solverdir/cbc/linux/i64/cbc).
# Building on an Apple Silicon Mac without this would default to arm64 and
# silently break the optimizer inside the container.
FROM --platform=linux/amd64 python:3.12-slim

# uv, since that's the toolchain this project already uses locally —
# also meaningfully faster than pip for container builds.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Copy just the dependency list first so Docker can cache this layer —
# rebuilds only reinstall packages when requirements.txt actually changes.
COPY requirements.txt .
RUN uv pip install --system --no-cache -r requirements.txt

COPY . .

ENV MCP_TRANSPORT=http
# PORT is injected by the hosting platform (Railway/Fly both set this);
# 8000 is only the local/default fallback.
ENV PORT=8000

EXPOSE 8000

CMD ["python", "server.py"]
