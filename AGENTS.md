# Project rules for EmberRoute (hackathon build, strict compliance)

You are helping build EmberRoute, a wildfire spread and evacuation planner for a hackathon. These rules apply to every task in this workspace.

## Non-negotiable data rules
1. NO dummy, mock, hardcoded or placeholder data in application code. Live inputs (fire detections, wind, humidity) must come from real APIs at runtime: NASA FIRMS and Open-Meteo. Static layers (elevation, land cover, roads) must come from official open datasets at runtime: AWS Terrain Tiles (Terrarium), ESA WorldCover, OpenStreetMap via osmnx.
2. Unit tests may build small synthetic grids or graphs procedurally, but only inside tests/. Application code must never import anything from tests/.
3. Caching is allowed for real fetched data. Every cached item must store source, URL, fetched_at (UTC) and TTL. Live layers (fires, weather) have a short TTL (default 10 minutes for weather, 15 minutes for fires). If a live fetch fails and a stale cache exists, return the stale data flagged is_stale=True and surface a warning. Never silently present stale data as fresh.
4. User what-if inputs (ignition point, wind override) are allowed ONLY when clearly labelled. Any result built from them must carry mode="SCENARIO" and the override must appear in provenance and warnings.
5. If real data is missing, degrade visibly (warning plus lower confidence). Never invent values.

## Engineering rules
- Python 3.11, type hints on public functions, docstrings stating units (metres, minutes, degrees) and coordinate order (lon, lat for GeoJSON and shapely; (lat, lon) is stated explicitly wherever used).
- Wind direction from Open-Meteo is the direction the wind comes FROM. Spread direction is (dir + 180) % 360. Bearings are degrees clockwise from north.
- Keep modules small and single-purpose, matching the repo layout in the task. Do not add frameworks that are not listed in the task.
- All network calls: timeout (default 20 s), up to 3 retries with exponential backoff, and clear exceptions (custom FeedError). No bare except.
- Configuration through core/config.py and .env (never hardcode keys; never print keys).
- Log with the logging module, structured one-line messages. No print() in library code.
- Every task must end with: (1) a short list of files changed, (2) the exact commands to run the acceptance checks, (3) the actual output of those commands, (4) known limitations.
- Do not expand scope. If something is ambiguous, choose the simplest option that satisfies the task, state the choice, and continue. Do not ask more than one clarifying question.
- Do not rewrite files outside the task's scope. Do not delete tests to make them pass.

## Team ownership and LLM rules
- Three people work in parallel on branches p1/core, p2/engine-api, p3/frontend. Edit ONLY the directories named in the task. If a change outside them is needed, stop and report it instead of editing.
- api/schemas.py is the API contract. Do not change existing field names or types after the contract freeze; only add optional fields.
- The LLM is an OpenAI-compatible client (Groq primary, Ollama backup). Do not add Gemini, LangChain or other agent frameworks. The LLM may choose tools and write briefings from verified facts; it may never compute fire arrival, routes or numbers.
- Token discipline: never send arrays or GeoJSON to an LLM; compact tool results; respect max_tokens and LLM_DAILY_TOKEN_BUDGET.
- Frontend (frontend/ only): no mock, fixture or hardcoded domain data in src/. Every displayed value comes from the API. A dev-only synthetic playground may live in frontend/dev/ and must never be imported by src/ or included in the production build.
