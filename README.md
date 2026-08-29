# Football Intelligence & Optimization Server

An MCP (Model Context Protocol) server that gives Claude live Fantasy Premier League data, expected-goals analytics, and a genuine constrained-optimization engine — so you can ask Claude to build your FPL squad, compare players, or get transfer advice, backed by real data rather than a hard-coded response.

## Why this exists

Built as a hands-on demonstration spanning three things I actually work with: data engineering (two independent live/scraped data sources, reconciled and cached), operations research (a real linear program, not a heuristic, deciding your squad), and shipping something that's actually deployed and connectable — not a notebook that only runs on my machine.

## What it can do

**Tools:**
| Tool | What it does |
|---|---|
| `get_players` | Browse/filter the live FPL player pool |
| `compare_players` | Side-by-side comparison of 2-5 players, enriched with xG/xA when available |
| `find_value_picks` | Ranks players by points-per-£m rather than raw points — surfaces undervalued performers |
| `get_fixture_difficulty` | FPL's own official difficulty rating, per team, for upcoming gameweeks |
| `optimize_fpl_squad` | Builds the mathematically optimal 15-man squad + starting XI + captain under a budget, using linear programming |

**Prompts** (ready-made structured asks an MCP client can surface directly):
| Prompt | What it chains together |
|---|---|
| `weekly_transfer_advice` | Fixtures + value picks + the optimizer, into one transfer recommendation |
| `captain_pick_advice` | Fixtures + form, into a captain/vice-captain recommendation |

## Example prompts to try

Once connected, just ask Claude things like:

- *"Build me the best FPL squad under £100m using a 4-4-2 formation"*
- *"Compare Haaland and Watkins — who's the better pick right now?"*
- *"Find me the best value defenders under £5m"*
- *"What are Arsenal's next 5 fixtures like?"*
- *"Who should I captain this week?"*

## How it's built

```
FPL API (live)  ──┐
                   ├──> player_pool.py ──> points_prediction.py ──┐
Understat (xG) ────┘         (data layer)    (scoring proxy)      │
                                                                    ▼
                                              optimize_squad.py (PuLP linear program)
                                                                    │
                                                                    ▼
                                          server.py (FastMCP: 5 tools + 2 prompts)
```

Two independent, unofficial data sources feed this: the FPL API (free, undocumented but stable) and Understat (scraped, less stable — handled with retries, caching, and graceful fallback to last season's data when the current season is too new to have stats yet). Points predictions use an empirical-Bayes shrinkage estimator so a one-match fluke doesn't skew the optimizer. The optimizer itself is a genuine mixed-integer linear program (via PuLP/CBC) — not a greedy heuristic — jointly solving squad selection, starting XI, and captaincy in one pass under FPL's real constraints (budget, position quotas, max 3 players per club).

## Tech stack

Python · [FastMCP](https://gofastmcp.com) · pandas · PuLP (CBC solver) · httpx · [understatapi](https://github.com/collinb9/understatAPI) · [uv](https://github.com/astral-sh/uv) · Docker

## Running it locally

```bash
uv venv
uv pip install -r requirements.txt
uv run fastmcp dev inspector server.py
```

That opens the MCP Inspector in your browser, where you can call any tool directly and see the raw response.

## Connecting to Claude Desktop

```bash
uv run fastmcp install claude-desktop server.py --name "Football Optimizer"
```

Restart Claude Desktop and it'll show up as a connected tool — from there you can just talk to it in plain English.

## Deployment

Runs as a standard containerized HTTP service (see `Dockerfile`) — set `MCP_TRANSPORT=http` and it serves over Streamable HTTP instead of stdio. A shared API key (`FOOTBALL_MCP_API_KEY` env var) and a per-IP rate limit (`middleware.py`) gate the public endpoint.

**Live server:** (https://football-mcp-server-production.up.railway.app/)

## A few honest notes

- This project was built and tested right as the 2026/27 Premier League season kicked off — several of the design decisions (graceful fallback when a data source has no data yet, empirical-Bayes shrinkage instead of raw season stats) exist specifically because early-season data is sparse, not because they're theoretically elegant.
- The xG integration matches players between two sources with no shared ID, by name — exact match first, fuzzy match as a fallback for accents/name variants, with anything it's not confident about explicitly flagged rather than silently guessed.
- Built iteratively over several weeks, story by story, against a tracked project plan with effort estimates — the commit history reflects that rather than one large dump.

## License

MIT
