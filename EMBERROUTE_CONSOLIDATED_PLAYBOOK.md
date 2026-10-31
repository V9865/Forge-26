# EmberRoute: Consolidated Execution Playbook (3 people, website, Groq/Ollama)
**Wildfire spread and evacuation planner. Track: Climate, Resource Infrastructure & Global Supply Resilience.**

> Tagline: *Fire maps tell you where it is burning. EmberRoute tells you when it reaches each village, which route still works, and the latest minute to leave. It re-plans as the wind changes.*

**Contents:** 0 Read this first, 1 Project definition, 2 Architecture and data sources, 3 API contract, 4 LLM strategy, 5 Algorithm specification, 6 Repository layout and interfaces, 7 Team split, timeline and gates, 8 Antigravity operating guide, 9 Prompts (shared, Person 1, Person 2, hardening, Person 3), 10 Demo plan, 11 Submission pack, 12 Edge cases, judge Q&A and risks, 13 Understanding checklist, 14 Final checklist.

---

## 0. Read this first

### 0.0 Who reads what

| Person | Role | Read in full | Run these prompts (section 9) |
|---|---|---|---|
| **Person 1** | Simulation core | 0, 1, 2, 3, 5, 6, 7, 8, 12, 13 | P1, P2, P3a, P4, P6, R-P8a, P12, P13 |
| **Person 2** | Evacuation, agent, API, deploy | 0, 1, 2, 3, 4, 5, 6, 7, 8, 12, 13 | P3b, P5, P7, R-P8b, A1, R-P11, P10 |
| **Person 3** | Frontend (exclusive) | 0, 1, 3, 7, 8, 12, 13, and 5.1-5.4 for concepts | F0-F8 (frontend track), plus the demo video and deck visuals |

This single file replaces `EMBERROUTE_EXECUTION_PLAYBOOK.md` and `EMBERROUTE_V2_THREE_PERSON_PLAN.md`. Prompt names with an `R-` prefix (R-P8a, R-P8b, R-P11) are the rewritten versions of the earlier P8 and P11; P9 (Streamlit) no longer exists and is replaced by A1 (API) and F0-F8 (frontend). Ownership conflicts found in the earlier drafts are already resolved here (for example `build_layers` lives in `core/layers.py`, owned by Person 1, and the pipeline smoke script is `scripts/smoke_pipeline.py`).

### 0.1 Timing rules (disqualification risk)
- **Do not write project code before the official hackathon start.** "Pre-existing project built before the event" is a disqualification clause. Before kickoff you may only: read this document, register accounts and API keys, install tools, and create an empty GitHub account or org.
- Create the repo at kickoff, with the first commit after kickoff. Commit after every prompt so the history shows work happening inside the window.
- All core logic (spread model, evacuation solver, agent workflow) must be written inside the window. Open-source libraries are fine.

### 0.2 How each rule is satisfied

| Rule | How EmberRoute complies |
|---|---|
| No dummy data | Fire detections (NASA FIRMS) and wind/humidity (Open-Meteo) are fetched live on every run. Static layers (terrain, land cover, roads) come from official open datasets at runtime. No hand-typed numbers anywhere in app code. |
| Scenario mode | A user-placed ignition or wind override is a labelled **what-if** on top of real terrain, fuel, roads and weather. It is shown on screen as `SCENARIO / OVERRIDE` and recorded in the provenance panel. |
| Live demo | App deployed on Hugging Face Spaces (Docker). Health-check script runs before every demo. |
| No pre-recorded demo | Demo video is a screen recording of the *live* app. Never a mockup. |
| Code ownership | Every prompt is followed by an "explain-back" step and every person has an understanding drill (section 13). |
| Edge cases | Prompt P10 hardening list (section 9.3), the edge-case matrix (section 12.1), the chaos drill script, and a fault-injection flag for demonstrating graceful degradation. |

### 0.3 Accounts and keys to get before kickoff
1. **NASA FIRMS MAP_KEY**: https://firms.modaps.eosdis.nasa.gov/api/ (free, emailed). Check status with `https://firms.modaps.eosdis.nasa.gov/mapserver/mapkey_status/?MAP_KEY=YOUR_KEY`.
2. **Groq API key** (free tier, https://console.groq.com) for the agent layer. Optionally install **Ollama** locally and pull a 7-8B model (`ollama pull qwen2.5:7b-instruct`) as a no-limit local backup. Any OpenAI-compatible provider works through `LLM_CHAIN` in `.env` (section 4).
3. **Hugging Face account** (Spaces, Docker SDK) for deployment.
4. **GitHub** account for the public repo.
5. Local: Python 3.11, **Node 20+** (Person 3 and the Docker build), Git, Docker (optional, for the local deploy test), Antigravity installed.

### 0.4 Key decisions

**Is this a website? Yes.** Judges open a URL. A Streamlit UI would leave a dedicated frontend person with almost nothing to do, since Streamlit hides the frontend. So the project uses a real web stack:

- **Backend:** FastAPI (Python) exposing the simulation as a JSON/GeoJSON API with background jobs.
- **Frontend:** React + TypeScript + Vite + Tailwind + MapLibre GL JS, owned entirely by Person 3.
- **One deployable:** a single Docker image on Hugging Face Spaces: FastAPI serves the built frontend at `/` and the API at `/api`. One URL, no CORS problems in production.

**LLM:** Groq (free tier, OpenAI-compatible API) as the hosted provider, Ollama as the local/offline backup, deterministic template as the last fallback. Reasons and the token budget are in section 4.

**Rubric note:** the technical-depth pillar penalises "superficial frontend wrappers". The frontend is the *presentation* of a real simulation and solver, so keep the depth visible: show the arrival bands, provenance, agent trace and validation panel in the UI.

---

## 1. Project definition

### 1.1 Problem statement (submission text, edit freely)
**Target issue & context.** Wildfires in forested hill regions and agricultural belts spread with wind and slope faster than residents can interpret a hotspot map. Authorities see *where* fire is detected, but not *when it will reach each settlement* or *which roads will still be passable by the time people reach them*. Evacuations fail when a route is cut by fire before travellers pass, and warnings arrive without a departure deadline.

**Target audience.** Villagers and tourists in fire-prone hill and forest regions; district disaster-management cells, forest departments and fire services; panchayat and municipal officials who issue evacuation orders.

### 1.2 Solution overview
EmberRoute ingests live satellite fire detections and live wind and humidity, builds a terrain-and-fuel model of the area, and runs a **wind-, slope- and fuel-aware fire arrival-time simulation**. A **time-dependent evacuation solver** then finds, for every threatened settlement, a route that finishes before fire reaches each road segment, and the **latest departure time** that still works. If no safe route exists, the settlement is flagged `TRAPPED` for shelter-in-place or airlift. An **autonomous agent** monitors the feeds, re-plans when conditions change, recovers from data failures, and writes a plain-language briefing in which every number is verified against the solver output.

### 1.3 USP (one line each)
1. Gives **arrival time and a depart-by deadline**, not just a hotspot map.
2. Routes are **fire-aware and time-aware**, and we quantify how often an ordinary shortest-route would have been cut.
3. The AI sits in a constrained role: the simulator and solver compute, the agent orchestrates and explains, and a guard blocks unverified numbers.
4. Validated against real FIRMS fire progression, with an area-matched naive baseline.

### 1.4 Rubric map

| Pillar (points) | Where we earn it |
|---|---|
| Technical depth (20) | Custom anisotropic spread engine, time-dependent Dijkstra, custom OSM/DEM/WorldCover pipeline, modular repo, caching, tests |
| AI reasoning and agentic execution (25) | Monitor, replan, tool-calling loop with retries and fallbacks, change detection, briefing guard (fact-ID citations), degraded-mode behaviour |
| Relevance, impact, USP (25) | Civic safety use case, naive-vs-aware metric, validation number, scalability to any region |
| Live demo and robustness (30) | Deployed Space, health check, edge cases, fault injection drill, stale-data banners, no crashes on bad input |

---

## 2. Architecture and data sources

### 2.1 System architecture (website)

```
 LIVE: NASA FIRMS, Open-Meteo        STATIC: Terrarium DEM, WorldCover, OSM
        |                                   |
        v                                   v
 +--------------------------- core/ (Python) -----------------------------+
 | data layer -> grid -> spread engine -> evacuation solver -> pipeline   |
 | agent: tools, orchestrator (Groq/Ollama), briefing + guard             |
 +---------------------------------+--------------------------------------+
                                   |
                           api/ (FastAPI, 1 worker)
                    jobs (thread pool) | monitor loop | GeoJSON converters
                                   |   JSON + GeoJSON over HTTP
                                   v
 +---------------- frontend/ (React + TS + MapLibre) -----------------------+
 | map | controls | settlement table | briefing | trace | provenance       |
 +-------------------------------------------------------------------------+
 One Docker image: uvicorn serves /api and the built frontend (frontend/dist)
```

### 2.2 Data sources with exact access details

| Layer | Source | Access | Notes |
|---|---|---|---|
| Active fires | NASA FIRMS | `GET https://firms.modaps.eosdis.nasa.gov/api/area/csv/{MAP_KEY}/VIIRS_SNPP_NRT/{west},{south},{east},{north}/{DAY_RANGE}`; add `/{YYYY-MM-DD}` for a start date | CSV columns include `latitude, longitude, acq_date, acq_time, confidence, frp, satellite`. VIIRS confidence is `l/n/h`; keep `n` and `h`. Use `world` instead of bbox to find active clusters. Also try `VIIRS_NOAA20_NRT`. |
| Weather | Open-Meteo forecast | `https://api.open-meteo.com/v1/forecast?latitude=..&longitude=..&hourly=wind_speed_10m,wind_direction_10m,wind_gusts_10m,relative_humidity_2m,temperature_2m&wind_speed_unit=ms&timezone=UTC&forecast_days=2&past_days=1` | No key. **Wind direction is the direction the wind comes FROM.** Spread direction is `(dir + 180) % 360`. |
| Historical weather (validation) | Open-Meteo archive | `https://archive-api.open-meteo.com/v1/archive` with `start_date`, `end_date`, same hourly variables | ERA5-based, for validation runs only |
| Elevation | AWS Terrain Tiles (Terrarium) | `https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png` | Decode: `elev_m = (R*256 + G + B/256) - 32768`. Zoom 12 is about 35 m per pixel at mid-latitudes. No key, no rasterio needed. |
| Fuel / land cover | ESA WorldCover v200 (2021) COGs | `https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map/ESA_WorldCover_10m_2021_v200_{TILE}_Map.tif` | `{TILE}` is the 3-degree tile lower-left corner, e.g. `N27E078`, `S03W060` (lat 2 digits, lon 3 digits). Read only a window with rasterio. |
| Roads, villages, shelters | OpenStreetMap via `osmnx>=2.0` | `ox.graph_from_bbox(bbox=(west,south,east,north), network_type="drive")`; `ox.features_from_bbox(bbox, tags=...)` | Villages: `place` in village, hamlet, town, suburb, locality. Shelters: `amenity` in school, hospital, community_centre. bbox order in osmnx 2.x is (left, bottom, right, top). |
| LLM | Groq (primary, free tier) and Ollama (local backup) | `openai` Python SDK with `base_url`, function calling | Model IDs come from `LLM_CHAIN` in `.env`; verify them in the Groq console and with `ollama list` |
| Basemap tiles | Carto dark raster (OSM standard tiles as fallback) | `https://{a-d}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png` | Attribution always shown: © OpenStreetMap contributors © CARTO |

### 2.3 WorldCover class to base rate of spread (heuristic, tuned in validation)

| Code | Class | Base ROS (m/min) |
|---|---|---|
| 10 | Tree cover | 3 |
| 20 | Shrubland | 8 |
| 30 | Grassland | 15 |
| 40 | Cropland | 10 |
| 50 | Built-up | 0.5 |
| 60 | Bare / sparse | 0.2 |
| 70 | Snow / ice | 0 |
| 80 | Open water | 0 |
| 90 | Herbaceous wetland | 1 |
| 95 | Mangroves | 2 |
| 100 | Moss / lichen | 2 |

These values live in `core/fire/fuel.py` as a documented table. They are *model parameters*, not data. The README must say so.

### 2.4 Assumptions register (state these on screen and in the README)
- **A1** The fire model is a simplified minimum-travel-time approximation (Huygens-style ellipse for wind, exponential slope factor). It is not a full Rothermel/FARSITE model.
- **A2** Spotting (embers jumping ahead), firebreaks (rivers, roads) and suppression are not modelled.
- **A3** 10 m wind is reduced to mid-flame wind with a factor (default 0.5).
- **A4** Evacuees travel at `speed_factor` (default 0.6) times the OSM-inferred road speed, with a safety buffer (default 10 min) before fire arrival.
- **A5** A road segment is unusable if fire reaches *any* point on it before the traveller exits it (conservative).
- **A6** "Safe target" means a road node the simulation does not burn within the horizon and that is at least `safe_dist_m` from the burned envelope.
- **A7** Ignitions come from VIIRS detections (confidence nominal or high) in the last 24 h and are treated as burning at t = 0.
- **A8** FIRMS NRT detections lag satellite overpass by up to ~3 h and are sparse. They are not a continuous perimeter.

---

## 3. API contract (freeze at hour 3)

Owner: Person 2 writes `api/schemas.py` (pydantic). FastAPI generates `/openapi.json`. Person 3 generates TypeScript types from it with `npx openapi-typescript http://localhost:8000/openapi.json -o frontend/src/api/types.ts`. **Changes after the freeze must be additive** (new optional fields) and announced in the team chat.

### 3.1 Endpoints

| Method and path | Purpose |
|---|---|
| `GET /api/health` | Live feed status: `{feeds: {firms, open_meteo, terrain, worldcover, overpass, llm}: {ok, latency_ms, detail, checked_at}}` |
| `GET /api/clusters?hours=24` | Active fire clusters from FIRMS: `[{id, lat, lon, count, total_frp, suggested_aoi}]` |
| `POST /api/plan` | Start a plan job. Body: `{aoi, mode: "LIVE"\|"SCENARIO", ignition?: {lat, lon}, wind_override?: {speed_ms?, dir_from_deg?}, resolution_m?: 60\|90\|120}`. Returns `{job_id}` immediately (HTTP 202). |
| `GET /api/jobs/{job_id}` | Poll status: `{status: queued\|running\|done\|error, stage, progress (0-1), trace[], result?, error?}` |
| `POST /api/monitor` | Enable/disable the auto-monitor: `{enabled, aoi, mode, ignition?, wind_override?, poll_s?}` |
| `GET /api/monitor` | `{enabled, last_cycle_utc, last_reasons[], current_job_id, next_poll_utc}` |
| `GET /api/assumptions` | Text of `docs/assumptions.md` (assumptions A1-A8 + parameters) |
| `GET /api/validation` | Parsed summary of `docs/validation.md` (if generated) so the UI can show the proof panel |

Errors always use `{error: {code, message}}` with a proper HTTP status. Codes: `NO_FIRE`, `FEED_DOWN`, `OSM_EMPTY`, `GRID_TOO_LARGE`, `NO_SETTLEMENTS`, `BAD_INPUT`, `NEEDS_SCENARIO`, `INTERNAL`.

### 3.2 `PlanResult` (the `result` field of a finished job)

```
mode: "LIVE" | "SCENARIO"
aoi: {west, south, east, north}
grid: {res_m, nx, ny}
wind: {source, is_override, is_stale, fetched_at_utc, now: {speed_ms, dir_from_deg, rh},
       series: [{t_utc, speed_ms, dir_from_deg, rh}]}          # for a small wind chart
detections: GeoJSON FeatureCollection<Point> {acq_time_utc, frp, confidence, satellite}
arrival_bands: GeoJSON FeatureCollection<Polygon|MultiPolygon> {t_min}   # cumulative: area burned by t_min,
                                                                         # every 30 min up to the horizon
settlements: GeoJSON FeatureCollection<Point> {id, name, status, fire_arrival_min|null,
             depart_by_min|null, route_travel_min|null, naive_cut|null, note}
routes: GeoJSON FeatureCollection<LineString> {settlement_id, kind: "aware"|"naive", cut: boolean}
naive_cut_segments: GeoJSON FeatureCollection<LineString> {settlement_id}
metrics: {n_threatened, n_evacuate, n_trapped, n_already_burning, n_naive_cut,
          n_rescued_by_replan, median_depart_by_min, min_depart_by_min,
          burned_ha_2h, burned_ha_6h, burned_ha_12h, downwind_bearing_deg}
briefing: {text, used_llm, provider, model, dropped_sentences, facts: {F1: "..."}}
provenance: [{name, source, url, fetched_at_utc, age_s, ttl_s, is_stale, note}]
warnings: [string]
trace: [{ts_utc, step, tool, status, duration_ms, note}]
```

`status` values: `NOT_THREATENED | EVACUATE | TRAPPED | ALREADY_BURNING`. All times in UTC ISO-8601; durations in minutes unless the name ends in `_s`.

### 3.3 Staged delivery (so the frontend always works against REAL data)
Person 2 delivers `PlanResult` in stages; later fields are simply absent or empty until ready, and the frontend treats them as optional:

| Stage | Hour | Fields that are real |
|---|---|---|
| v0 | ~5 | mode, aoi, grid, wind, detections, provenance, warnings, trace |
| v1 | ~10 | + arrival_bands, burned-area metrics |
| v2 | ~14 | + settlements, routes, naive_cut_segments, evacuation metrics |
| v3 | ~18 | + briefing, monitor endpoints, validation endpoint |

### 3.4 Job flow
`POST /api/plan` -> `job_id` -> poll `GET /api/jobs/{id}` every 1 s (backoff to 2 s after 20 s) until `done` or `error`. The `trace` array grows while running, so the UI can show live stage names ("Fetching fire detections", "Running spread simulation", ...). A new request with an identical input hash within 60 s returns the cached job.

---

## 4. LLM strategy (Groq primary, Ollama backup)

### 4.1 Why this fixes the token problem
- **Groq** has a free tier with an **OpenAI-compatible** API (`https://api.groq.com/openai/v1`) and supports tool calling. Free-tier limits (requests/min, tokens/min, tokens/day) differ per model and change over time, so check the limits page in the Groq console and put the numbers in `docs/llm_limits.md`.
- **Ollama** runs models locally (`http://localhost:11434/v1`, also OpenAI-compatible). No token cap, but you need a laptop that can run a 7-8B model. Use it for local development and as an offline backup for the demo laptop. A free CPU Hugging Face Space cannot host it usefully.
- One client library (`openai` Python package with a `base_url`) covers both. The same code then works with any other OpenAI-compatible provider.

### 4.2 Provider chain
`LLM_CHAIN` is an ordered list. On a 429, timeout, or error the next entry is tried, and the last fallback is the deterministic template. Example (verify model IDs in the Groq console and `ollama list`, because model names change):
```
LLM_CHAIN=groq:llama-3.3-70b-versatile,groq:llama-3.1-8b-instant,ollama:qwen2.5:7b-instruct
LLM_PLANNER_MODEL=groq:llama-3.1-8b-instant      # tool-choice loop (small and cheap)
LLM_BRIEFING_MODEL=groq:llama-3.3-70b-versatile  # one call per cycle
```

### 4.3 Token budget (target: under about 6k tokens per plan cycle)

| Call | Input cap | Output cap | Notes |
|---|---|---|---|
| Planner (tool loop) | system prompt about 250 tokens; each tool result compressed to under 300 tokens; at most 5 calls | `max_tokens=150` | Small model. Default tool order is stated in the prompt, so the model rarely needs to reason. |
| Briefing | at most about 1,200 tokens of facts (8 settlements, key metrics) | `max_tokens=350` | Larger model, one call per cycle. |
| Monitor polls | 0 tokens | 0 | LLM runs only when a change trigger fires. |

More rules: cache the briefing by a hash of the facts; on 429 read the `retry-after` header and wait at most 5 s before falling to the next provider; keep a daily token counter (in memory plus a log line) and stop calling the LLM when it passes `LLM_DAILY_TOKEN_BUDGET`, using the template instead; never send raw GeoJSON or arrays to the LLM.

### 4.4 Honesty on screen
The briefing card always shows `provider/model` or "Template briefing", and whether the guard dropped sentences. Judges respect transparency, and it proves the system works with no LLM at all.

---

## 5. Algorithm specification

### 5.1 Grid
- Local metric grid in the AOI's UTM zone (EPSG 326xx north / 327xx south via pyproj).
- Resolution 90 m by default (about 220 x 220 cells for a 20 x 20 km AOI). Configurable between 30 and 150 m. Maximum 400 x 400 cells.
- Arrays are `(ny, nx)`, row 0 is the northern edge.
- Layers: `elevation`, `fuel_class`, `base_ros`.

### 5.2 Spread engine (anisotropic earliest-arrival Dijkstra)
For every move from cell *s* to neighbour *d* (8-connected) at current time *t* (minutes since now):

1. `h = min(int(t // 60), H - 1)`, the hour index into the wind series.
2. `U_mid = wind_speed_10m[h] * midflame` (m/s). `mph = U_mid * 2.237`.
3. Length-to-breadth ratio (Anderson 1983): `LB = 0.936*exp(0.2566*mph) + 0.461*exp(-0.1548*mph) - 0.397`, capped at `lb_cap = 8`. At zero wind LB = 1, so spread is isotropic.
4. `e = sqrt(LB^2 - 1) / LB`.
5. `wind_to = (wind_dir_from[h] + 180) % 360`. `theta` = angle between the move bearing and `wind_to`.
6. `ros_head = base_edge * (1 + k_wind * U_mid) * f_moist[h] * ros_scale`, where `base_edge = 0.5*(base_ros[s] + base_ros[d])`.
7. `f_moist = clip(1.5 - 1.2 * RH/100, 0.3, 1.5)`.
8. Wind direction factor (ellipse): `f_dir = (1 - e) / (1 - e*cos(theta))`. This is 1 downwind and `(1-e)/(1+e)` upwind.
9. Slope: `g = (z_d - z_s) / dist`; `f_slope = clip(exp(3.533 * sign(g) * |g|^1.2), 0.25, 6)`.
10. `ros_edge = ros_head * f_dir * f_slope`. If `base_ros[d] <= 0.01`, the move is blocked.
11. `dt = dist / ros_edge`; `arrival[d] = min(arrival[d], arrival[s] + dt)`; stop expanding beyond `horizon_min` (default 720).

Because wind is looked up at the current arrival time, a forecast wind shift is reflected in the simulation itself. Output is `arrival_min`, a float32 array with `inf` for cells that do not burn within the horizon.

Performance target: under 5 s for 250 x 250 cells. Write plain NumPy and `heapq` first, test it, and only then add numba if it misses the target.

### 5.3 Evacuation solver (time-dependent Dijkstra)
1. Build the OSM drive graph. Add speeds and travel times (`ox.routing.add_edge_speeds` with sensible fallbacks, then `add_edge_travel_times`). `tt_min = length_m / (speed_kph * speed_factor * 1000/60)`.
2. For every edge, sample points along its geometry every `<= res_m` metres and take `edge_fire_min = min(arrival_min at samples)`. Store as an edge attribute (`inf` if never burned).
3. A traveller who reaches node *u* at time `t_u` can use edge (u, v) iff `t_u + tt_min + buffer_min <= edge_fire_min`.
4. Run earliest-arrival Dijkstra from the settlement's snapped node, starting at departure time `d`, until a safe target node is settled.
5. **Safe targets:** nodes with `arrival_min = inf` and distance to the nearest burned cell of at least `safe_dist_m` (use `scipy.ndimage.distance_transform_edt` on the burned mask). Nodes near a shelter (school, hospital, community centre within 300 m) are flagged as shelters.
6. **Depart-by:** feasibility is monotone in `d` (later is harder), so binary-search the largest feasible `d` in `[0, horizon]` to 1-minute tolerance.
7. **Status per settlement:**
   - `NOT_THREATENED`: settlement cell does not burn within the horizon.
   - `EVACUATE`: route exists at `d = 0`; report route, travel minutes, depart-by.
   - `TRAPPED`: no feasible route at `d = 0`; recommend shelter-in-place or airlift.
   - `ALREADY_BURNING`: fire arrival at the settlement is at or before t = 0.

### 5.4 Naive baseline (the USP number)
Same targets, same speeds, but route chosen by plain shortest travel time with no fire awareness. Then check that route against `edge_fire_min` using the rule in 5.3. Report:
- Number of settlements whose naive route would have been **cut by fire**.
- Number of those where EmberRoute found a **working alternative**.

### 5.5 Validation (see Prompt 6)
For each past fire event: seed the model with detections up to `T0`, simulate with historical ERA5 wind, then measure how many *later* FIRMS detections fall inside the predicted burned area. Compare against an **area-matched isotropic baseline** (constant ROS, tuned so total burned area equals the model's). Parameters (`k_wind`, `midflame`, `ros_scale`) are fitted on two events and evaluated on a held-out third event.
Metrics: recall of future detections within predicted area; predicted area; bearing error of the fire's centroid displacement. FIRMS is sparse, so **do not claim a true IoU**. Say "recall of observed detections".

### 5.6 Agent behaviour and guardrails
- **Monitor loop:** poll fire and weather feeds. Re-simulate only when a trigger fires: new detections in the AOI, mean wind direction shift above 30 degrees, wind speed change above 25%, or manual refresh.
- **Tools** (typed JSON schemas): `get_fire_detections`, `get_weather`, `build_layers`, `run_spread`, `plan_evacuation`, `compare_baseline`, `get_settlement_detail`.
- **Self-correction rules:**
  - No detections found: ask for or offer scenario ignition. Never invent one silently.
  - Weather API fails: retry with backoff, then use the last real reading, show a stale-data banner with age, mark confidence `DEGRADED`.
  - WorldCover unavailable: use uniform fallback fuel, show `FUEL UNKNOWN (degraded)`.
  - Zero threatened settlements while fire is present: extend horizon or AOI once, then report plainly.
  - OSM Overpass timeout: retry on alternate endpoint, then fall back to disk-cached graph for the same bbox.
- **Briefing guard:** the code builds a list of facts (`F1..Fn`, each a short sentence with its numbers). The LLM must write the briefing citing fact IDs like `[F3]`. The guard drops any sentence with no valid citation or with a number not present in the cited fact. If fewer than 2 sentences survive, or the LLM call fails, a deterministic template briefing is used.

---

## 6. Repository layout and interfaces

### 6.1 Layout

```
emberroute/
  README.md
  AGENTS.md                  # rules for Antigravity (P0), committed first
  requirements.txt           # Python deps (no Streamlit)
  Dockerfile                 # multi-stage: build frontend, run FastAPI (R-P11)
  .env.example
  core/
    config.py  models.py  geo.py  cache.py  errors.py      # P1
    layers.py                # build_layers(aoi) -> Layers            (P3a)
    data/
      firms.py weather.py health.py                        # P2
      terrain.py landcover.py                              # P3a
      osm.py                                               # P3b
    fire/
      fuel.py spread.py bands.py baseline.py validate.py   # P3a, P4, P6
    evac/
      graph_prep.py planner.py naive.py                    # P5
    agent/
      guard.py briefing.py                                 # R-P8a (Person 1)
      llm.py tools.py orchestrator.py trace.py             # R-P8b (Person 2)
    pipeline.py              # run_pipeline()                         # P5, P7
  api/                       # FastAPI (A1, Person 2)
    main.py schemas.py jobs.py geojson.py monitor.py
  frontend/                  # React + TS + Vite + MapLibre (Person 3)
    src/ api/ map/ panels/ state/ lib/ styles/
    dev/                     # dev-only playground, never in the build
    e2e/  scripts/check-no-fixtures.mjs  dist/ (build output)
  scripts/
    health_check.py render_spread.py validate_spread.py prefetch.py
    llm_selftest.py agent_demo.py smoke_pipeline.py api_smoke.py
    smoke_test.py chaos_drill.py
  tests/ unit/ integration/ api/
  docs/ assumptions.md validation.md validation_events.json calibrated_params.json
        llm_limits.md deploy.md architecture.md RELEASE_CHECK.md screenshots/ figures/
```

### 6.2 Core models (`core/models.py`)
```python
AOI(west, south, east, north)                       # + center, width_km, height_km
GridSpec(epsg, x0, y0, res_m, nx, ny)               # top-left corner in metres
FireDetection(lat, lon, acq_time_utc, frp, confidence, satellite)
WindSeries(start_utc, speed_ms[], dir_from_deg[], rh[], temp_c[],
           source, fetched_at_utc, is_override, is_stale)
Layers(grid, elevation, fuel_class, base_ros, provenance{})
SpreadParams(k_wind=0.25, midflame=0.5, ros_scale=1.0, lb_cap=8, horizon_min=720)
SpreadResult(grid, arrival_min, ignitions[], params, runtime_s)
Settlement(id, name, lat, lon, node)
EvacParams(speed_factor=0.6, buffer_min=10, safe_dist_m=1500)
SettlementPlan(settlement, status, fire_arrival_min, depart_by_min,
               route_lonlat[], route_travel_min, naive_cut: bool, note)
PipelineResult(aoi, mode, detections[], wind, spread, plans[], metrics{},
               provenance[], warnings[], trace[])
```

---

## 7. Team split, timeline and gates

### 7.1 Ownership

| | **Person 1: Simulation core** | **Person 2: Evacuation, agent, API, deploy** | **Person 3: Frontend (exclusive)** |
|---|---|---|---|
| Directories (edit only these) | `core/data/{firms,weather,terrain,landcover,health}.py`, `core/geo.py`, `core/layers.py`, `core/fire/**`, `core/agent/{guard,briefing}.py`, `docs/validation*`, `docs/assumptions.md`, `scripts/{render_spread,validate_spread}.py` | `core/evac/**`, `core/data/osm.py`, `core/pipeline.py`, `core/agent/{llm,tools,orchestrator,trace}.py`, `api/**`, `Dockerfile`, `scripts/{smoke_test,smoke_pipeline,api_smoke,chaos_drill,llm_selftest,agent_demo}.py` | `frontend/**` only |
| Prompts | P1, P2, P3a (terrain, landcover, layers), P4, P6, R-P8a (guard + briefing), P12, P13 | P3b (OSM), P5, P7, R-P8b (llm, tools, orchestrator), A1, R-P11, P10 | F0-F8 |
| Shared files (change via PR and announce) | `core/models.py`, `core/config.py` (owner: P1) | `api/schemas.py` (owner: Person 2) | `frontend/src/api/types.ts` (generated, never hand-edited) |
| Must be able to explain | Data layer, grid, spread equations, validation | Evacuation solver, naive baseline, agent loop, API jobs, deployment | The API contract, what each UI element shows and why, the data flow from click to map, and, at a conceptual level, what arrival time and depart-by mean |

Person 3 owns frontend design exclusively, and also owns the screenshots, the demo-video recording and the visuals for the deck.

### 7.2 Hour-by-hour

**First 15 minutes (Person 1):** create the empty GitHub repo, commit `AGENTS.md` (P0) and `.gitignore`, create branches `p1/core`, `p2/engine-api`, `p3/frontend`, push. Everyone clones. Person 3 can start immediately because `frontend/` does not depend on P1.

| Hours | Person 1 | Person 2 | Person 3 |
|---|---|---|---|
| 0-1 | P1 scaffold (models, geo, cache, config), push | Python env, Groq key tested, draft `api/schemas.py` from section 3 | F0 rules, F1 scaffold: Vite + React + TS + Tailwind + MapLibre showing a basemap |
| 1-3 | P2: FIRMS, Open-Meteo, health, clusters | P3b: OSM graph, settlements, shelters; FastAPI skeleton, job manager, static serving | F1: design tokens, layout shell, typed API client skeleton |
| **3 (M1, G1)** | Feeds verified live | **Contract freeze**; `/api/health` and `/api/clusters` live | Types generated; health and clusters panels on real data |
| 3-7 | P3a: terrain, landcover, `core/layers.build_layers` | `/api/plan` v0 (detections, wind, provenance, trace); start P5 evac solver with synthetic tests | F2 map core, F3 control panel (area, mode, click-to-ignite, wind override), job polling UI |
| **7 (G2)** | Layers render for the default AOI | Road graph renders | |
| 7-11 | P4: spread engine, `core/fire/bands.py`, render script | P5: evac solver and naive baseline | F2b: arrival bands layer and time slider |
| **10-11 (M2, G3)** | Arrival map is physically sensible | `/api/plan` v1 with `arrival_bands` | Bands render on the real map |
| 11-14 | R-P8a: `guard.py`, `briefing.py`, tests; spread performance | `pipeline.run_pipeline` end to end (P5 part 4, P7); settlements and routes in the API | F4: settlements, routes, metric cards, table with map sync |
| **14-15 (M3, G4)** | | `/api/plan` v2; at least one EVACUATE, ideally one TRAPPED, naive-cut count | Settlements and routes on the real map; naive toggle |
| 14-17 | P6: validation events, calibration, `docs/validation.md` | R-P8b: llm chain, tools, orchestrator, monitor; **R-P11 deploy by hour 17** | F5: briefing, trace, provenance panels, freshness banners |
| **17 (M4, G5)** | | Public URL up (single container) | Frontend build served by the container |
| 17-20 | P10 data/spread items (1, 2, 3, 6, 9, 10, 13); `/api/validation` data | `/api/plan` v3; monitor; P10 other items; chaos drill; smoke tests | F6: monitor toggle, error/empty/loading states |
| **20 (M5, G6)** | | Briefing, trace and monitor work end to end | |
| 20-22 | P12 README and docs; P13 compliance scan | Fix integration bugs, performance | F7: responsive, accessibility, polish; F8 Playwright e2e |
| **22 (M6)** | **Feature freeze** | | |
| 22-24 | Full QA and pre-demo checklist; explain-back drills | Demo drive: backup AOIs and scenario ignition | Record the demo video, capture screenshots, deck visuals |

**Gates** (must pass to continue; if a gate slips by more than one hour, cut scope using section 12.4):
- **G1 (hour 3):** FIRMS and Open-Meteo return real data today.
- **G2 (hour 7):** layers render for the default AOI.
- **G3 (hour 11):** arrival map elongates downwind and runs faster uphill.
- **G4 (hour 15):** at least one `EVACUATE`, ideally one `TRAPPED`, with a naive-cut count.
- **G5 (hour 17):** public URL works (deploy by hour 17 at the latest).
- **G6 (hour 20):** briefing, trace and monitor work on the deployed app.

**Solo or two-person fallback:** if a teammate drops out, Person 2's cut list (section 12.4) applies first; Person 1 absorbs the validation endpoint and data-side hardening; Person 3's scope shrinks to F1-F5 plus F8.

### 7.3 Git and Antigravity discipline
- Three branches: `p1/core`, `p2/engine-api`, `p3/frontend`. Merge to `main` through a PR at each milestone M1-M6 (quick review by one other person) and pull `main` before starting a new prompt.
- Directory ownership prevents merge conflicts. Tell each Antigravity agent which directories it may edit (section 6.1 rule). Anything outside a person's directories goes through the owner.
- Commit after every prompt with the message `P<n>: ...` or `F<n>: ...`. Commit history must start after kickoff.
- Daily stand-up isn't needed. Instead use a shared chat with three message types: `API CHANGE`, `BLOCKED`, `MERGED M<n>`.
- If someone is blocked on another person's output for more than 30 minutes, the blocked person works on the next item in their own list and the owner posts an ETA.

---

## 8. Antigravity operating guide

- **One prompt per task thread.** Start a fresh agent conversation for each prompt below and paste it whole. Each prompt restates the context it needs, so the agent does not rely on earlier chat.
- **Use Planning mode** for P4, P5, R-P8a, R-P8b, A1 and F2 (algorithmic or multi-file). Read the implementation plan the agent proposes *before* approving it. Reject plans that add mock data, extra frameworks or features not in the prompt. Fast mode is fine for small fixes and P12.
- **Rules file:** paste Prompt 0 as the workspace rules (Antigravity workspace rules / customizations) and also save it as `AGENTS.md` in the repo root, so it applies whichever way your version loads rules. Person 3 additionally uses F0 as the rules for frontend work.
- **After every prompt:** run the acceptance commands yourself in the terminal, then `git add -A && git commit -m "P<n>: <summary>"` (or `F<n>:` for frontend prompts)`.
- **Explain-back (do this after every prompt):** paste the explain-back prompt in section 8.1 into the same thread. This is how every teammate meets the code-ownership rule.
- **If something breaks:** use the debug prompt in section 8.2. Do not ask for a "rewrite everything".

### 8.1 Explain-back prompt (use after each prompt)
````
Explain what you just built so I can defend it to judges.
1. List each file you created or changed and its single responsibility.
2. Walk through the data flow of the main function step by step, naming the real inputs and outputs.
3. State every assumption and heuristic parameter, and where it is defined.
4. List 5 questions a judge could ask about this code and give a one-paragraph answer for each.
5. Point out anything you were unsure about or simplified.
Do not change any code in this step.
````

### 8.2 Debug prompt template
````
Bug report.
Command run: <paste command>
Expected: <what should happen>
Actual: <paste full error or wrong output>
Rules: find the root cause before changing code, explain it in two sentences, make the smallest fix, add or update a test that would have caught it, then re-run the failing command and the test suite and show me the output. Do not add mock data to make it pass.
````
- **Model hint:** if your Antigravity version lets you pick the model per thread, use the strongest available for P4, P5, A1 and F2, and a faster one for scaffolding, docs and tests.
- **Stay in your lane:** every prompt names the files it may edit. If an agent wants to change anything else, stop and tell the owner.


---

## 9. Prompts

Paste each prompt whole into a fresh Antigravity thread, in the order shown for your track. Timing is in section 7.2. Every prompt restates its own context and names the files it may edit.

| Prompt | Owner | Purpose |
|---|---|---|
| P0 | All (Person 1 commits it) | Project rules (AGENTS.md) |
| P1, P2, P3a, P4, P6, R-P8a, P12, P13 | Person 1 | Scaffold, live feeds, terrain and fuel, spread engine and bands, validation, facts and guard, docs, QA |
| P3b, P5, P7, R-P8b, A1, R-P11, P10 | Person 2 | OSM, evacuation solver, pipeline, LLM client and orchestrator, FastAPI, deploy, hardening |
| F0-F8 | Person 3 | The whole frontend |

### 9.0 Shared rules
### P0: Project rules (Person 1 commits this as AGENTS.md at kickoff; all three paste it as workspace rules)
````
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
````

### 9.1 Person 1 track: simulation core

### P1: Scaffold, config, cache, models (Person 1)
````
Context: EmberRoute is a wildfire spread and evacuation planner. Rules are in AGENTS.md / workspace rules. This task creates the project skeleton only.

Task: create the repository skeleton exactly as follows.

Directories and empty __init__.py files: core/, core/data/, core/fire/, core/evac/, core/agent/, api/, scripts/, tests/unit/, tests/integration/, tests/api/, docs/. Do NOT create app/ or frontend/ (the frontend is created by Person 3).

Files to implement fully:

1. requirements.txt with pinned minimum versions: numpy, scipy, pandas, requests, pillow, pyproj, shapely>=2, rasterio, networkx, osmnx>=2.0, geopandas, pydantic>=2, python-dotenv, matplotlib, scikit-learn, openai>=1.40, fastapi, uvicorn[standard], httpx, pytest, pytest-asyncio, tenacity, numba (optional, in a separate requirements-optional.txt).

2. .env.example with: FIRMS_MAP_KEY=, LLM_CHAIN=groq:llama-3.3-70b-versatile,groq:llama-3.1-8b-instant,ollama:qwen2.5:7b-instruct, LLM_PLANNER_MODEL=groq:llama-3.1-8b-instant, LLM_BRIEFING_MODEL=groq:llama-3.3-70b-versatile, GROQ_API_KEY=, GROQ_BASE_URL=https://api.groq.com/openai/v1, OLLAMA_BASE_URL=http://localhost:11434/v1, LLM_DAILY_TOKEN_BUDGET=100000, LLM_TIMEOUT_S=20, POLL_S=60, CACHE_DIR=.cache, SIMULATE_API_FAILURE= (empty or one of firms, open_meteo, worldcover, overpass, llm), LOG_LEVEL=INFO, API_PORT=8000, CORS_ORIGINS=http://localhost:5173. (Model IDs are examples; they are verified in the Groq console and with `ollama list` by Person 2.) Add .env and .cache to .gitignore.

3. core/config.py: load .env with python-dotenv; expose a frozen Settings dataclass with those values plus defaults: HTTP_TIMEOUT_S=20, HTTP_RETRIES=3, WEATHER_TTL_S=600, FIRES_TTL_S=900, GRID_RES_M=90, MAX_GRID_CELLS=400, HORIZON_MIN=720, and all the LLM and API settings from item 2. A function get_settings() that is cached.

4. core/models.py: implement the models listed below as pydantic v2 models (or dataclasses where numpy arrays are held, with arbitrary_types_allowed). Include helper properties. AOI: west, south, east, north; validate west<east, south<north, and a max extent of 0.6 degrees per side; properties center (lat, lon), width_km, height_km. GridSpec(epsg, x0, y0, res_m, nx, ny). FireDetection(lat, lon, acq_time_utc, frp, confidence, satellite). WindSeries(start_utc, speed_ms list, dir_from_deg list, rh list, temp_c list, source str, fetched_at_utc, is_override bool, is_stale bool). Layers(grid, elevation, fuel_class, base_ros, provenance dict). SpreadParams(k_wind=0.25, midflame=0.5, ros_scale=1.0, lb_cap=8.0, horizon_min=720). SpreadResult(grid, arrival_min ndarray, ignitions list, params, runtime_s). Settlement(id, name, lat, lon, node int|None). EvacParams(speed_factor=0.6, buffer_min=10, safe_dist_m=1500). SettlementPlan(settlement, status literal NOT_THREATENED|EVACUATE|TRAPPED|ALREADY_BURNING, fire_arrival_min float|None, depart_by_min float|None, route_lonlat list of (lon, lat), route_travel_min float|None, naive_cut bool|None, note str). ProvenanceRecord(name, source, url, fetched_at_utc, ttl_s, is_stale, note). PipelineResult(aoi, mode literal LIVE|SCENARIO, detections, wind, spread, plans, metrics dict, provenance list, warnings list, trace list).

5. core/cache.py: a disk cache under CACHE_DIR with functions get(key, ttl_s) -> (payload bytes|None, meta), put(key, payload, source, url), and a ProvenanceRecord factory. Keys are hashed filenames; metadata stored as a sidecar JSON with source, url, fetched_at_utc. Also expose cached_or_fetch(key, ttl_s, fetch_fn, allow_stale=True) returning (payload, ProvenanceRecord) which: returns fresh cache if within TTL; else calls fetch_fn; on FeedError returns stale cache flagged is_stale=True if available, else re-raises.

6. core/geo.py: functions utm_epsg_for(lat, lon), make_grid(aoi, res_m, max_cells) which returns GridSpec covering the AOI in UTM (reduce resolution automatically by increasing res_m until cells <= max_cells, and log it), cell_centers_lonlat(grid) returning (lon, lat) arrays shape (ny, nx), lonlat_to_rc(grid, lon, lat) and rc_to_lonlat(grid, r, c) (vectorised, row 0 is the northern edge), bearing_deg(dr, dc) for a grid move (clockwise from north, row increases southward), and haversine_m.

7. core/__init__.py exposing nothing heavy. A custom exception class FeedError(Exception) in core/errors.py.

8. scripts/__init__.py and tests/conftest.py (adds the repo root to sys.path and registers the `integration` pytest marker that is skipped unless RUN_INTEGRATION=1).

9. tests/unit/test_geo.py: tests for lonlat_to_rc and rc_to_lonlat round trip (error under half a cell), bearing_deg for the 8 directions, make_grid never exceeding max_cells, and AOI validation errors.
10. tests/unit/test_cache.py: tests for TTL expiry, stale fallback when fetch_fn raises FeedError, and re-raise when no cache exists.

Acceptance: `pytest tests/unit -q` passes; `python -c "from core.config import get_settings; print(get_settings())"` prints the settings with secrets masked. Show the output, then push to p1/core and merge to main so Persons 2 and 3 can pull.
````

### P2: Live feeds (FIRMS + Open-Meteo) and health check (Person 1)
````
Context: EmberRoute (see AGENTS.md). Skeleton from P1 exists (core/config.py, core/models.py, core/cache.py, core/errors.py, core/geo.py). This task builds the LIVE data layer. No mock data anywhere in application code.

Task:

1. core/data/firms.py
   - fetch_detections(aoi: AOI, hours: int = 24, source: str = "VIIRS_SNPP_NRT") -> tuple[list[FireDetection], ProvenanceRecord].
   - URL: https://firms.modaps.eosdis.nasa.gov/api/area/csv/{MAP_KEY}/{SOURCE}/{west},{south},{east},{north}/{DAY_RANGE} where DAY_RANGE = ceil(hours/24) (min 1, max 5). Parse the CSV with pandas. Build acq_time_utc from acq_date and acq_time (HHMM, zero-padded). Keep VIIRS confidence in {"n","h","nominal","high"}; keep MODIS confidence >= 30 if the MODIS source is used. Filter to rows within the last `hours` hours relative to now (UTC). Never include the MAP_KEY in logs or provenance URLs (mask it as ***).
   - Also try VIIRS_NOAA20_NRT and merge results, de-duplicating detections closer than 100 m and 10 minutes.
   - find_active_clusters(hours: int = 24, top_n: int = 5) -> list[dict]: request the world endpoint (.../world/1), cluster detections with a simple grid binning of 0.25 degrees (no sklearn needed), compute count and total FRP per bin, merge adjacent bins, return top_n clusters as dicts with center lat, lon, count, total_frp, and a suggested AOI of 0.2 x 0.2 degrees around the highest-FRP-weighted centroid. This powers the "auto-select active fire" button.
   - Use cached_or_fetch with FIRES_TTL_S. Honour SIMULATE_API_FAILURE=firms by raising FeedError at the fetch step (used to demonstrate fallback behaviour, not to supply data).
   - Errors: missing MAP_KEY -> FeedError with a clear message. HTTP 4xx/5xx or an HTML or text error body (FIRMS returns text errors with status 200 sometimes) -> FeedError. Empty valid CSV -> return an empty list (not an error).

2. core/data/weather.py
   - fetch_wind_series(lat: float, lon: float, hours_ahead: int = 24) -> tuple[WindSeries, ProvenanceRecord] using https://api.open-meteo.com/v1/forecast with hourly=wind_speed_10m,wind_direction_10m,wind_gusts_10m,relative_humidity_2m,temperature_2m, wind_speed_unit=ms, timezone=UTC, past_days=1, forecast_days=2. Slice the series so index 0 is the current UTC hour. Validate no None values (forward-fill at most 2 consecutive gaps, otherwise FeedError). Series length must be at least hours_ahead.
   - apply_override(series, speed_ms=None, dir_from_deg=None) -> WindSeries: returns a copy with is_override=True and source set to "USER OVERRIDE (what-if)". Overrides apply to all hours.
   - Honour SIMULATE_API_FAILURE=open_meteo.
   - Cache with WEATHER_TTL_S.
   - fetch_wind_history(lat, lon, start_date, end_date) for validation using https://archive-api.open-meteo.com/v1/archive with the same variables.

3. core/data/health.py: check_all() returns a dict of feed -> {ok: bool, latency_ms, detail, fetched_at}. Checks FIRMS (key status endpoint https://firms.modaps.eosdis.nasa.gov/mapserver/mapkey_status/?MAP_KEY=..., plus a tiny area query), Open-Meteo, the AWS Terrarium tile endpoint (fetch one tile), WorldCover (HTTP HEAD on one tile URL), Overpass (a tiny osmnx query or the status endpoint). Never fails the whole call if one check fails.

4. scripts/health_check.py: prints a table from check_all() and exits non-zero if FIRMS or Open-Meteo is down.

5. tests/unit: parse-only tests for the FIRMS CSV parser and the Open-Meteo JSON slicer using small literal strings defined inside the test file. tests/integration (marked with @pytest.mark.integration, skipped unless RUN_INTEGRATION=1): fetch real data for a small AOI and assert the schema.

Acceptance: `pytest tests/unit -q` passes; `python scripts/health_check.py` shows every feed OK with real latency numbers; `python -c "from core.data.firms import find_active_clusters; print(find_active_clusters())"` prints real clusters. Show the real output. Report the number of detections returned and the timestamp of the newest one.
````

### P3a: Terrain, land cover, fuel and layer builder (Person 1)
````
Context: EmberRoute (see AGENTS.md). P1 and P2 are done. This task builds the STATIC terrain and fuel layers from official open datasets and assembles them on the simulation grid. No mock data. You may only edit core/data/terrain.py, core/data/landcover.py, core/fire/fuel.py, core/layers.py, scripts/prefetch.py and tests for them.

Task:

1. core/data/terrain.py
   - get_elevation(grid: GridSpec) -> tuple[np.ndarray, ProvenanceRecord]: elevation in metres, shape (ny, nx), float32.
   - Source: AWS Terrain Tiles Terrarium PNGs at https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png. Use zoom 12. Compute the lon/lat bounds of the grid (with a 1-cell margin), enumerate the slippy-map tiles covering it, download them (cached on disk, TTL 30 days), decode each with elevation = (R*256 + G + B/256) - 32768, mosaic into one array with known lon/lat bounds, then sample the mosaic at each grid cell centre (lon/lat from core.geo.cell_centers_lonlat) with bilinear interpolation (scipy.ndimage.map_coordinates). Handle Web-Mercator pixel math correctly (do not treat pixels as equal in latitude).
   - compute_slope(elevation, res_m) -> (dz_dx, dz_dy, slope_deg) using np.gradient with res_m spacing; document the sign convention (x east, y south because rows increase southward).

2. core/data/landcover.py
   - get_fuel_class(grid: GridSpec) -> tuple[np.ndarray, ProvenanceRecord]: uint8 WorldCover class codes, shape (ny, nx).
   - Tile id from the AOI: lat0 = floor(lat/3)*3, lon0 = floor(lon/3)*3, tile = f"{'N' if lat0>=0 else 'S'}{abs(lat0):02d}{'E' if lon0>=0 else 'W'}{abs(lon0):03d}". URL: https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map/ESA_WorldCover_10m_2021_v200_{tile}_Map.tif
   - Open with rasterio (HTTP range reads), read only the window covering the grid bounds using rasterio.windows.from_bounds, then sample at each grid cell centre by nearest neighbour. If the grid spans multiple tiles, read each needed tile and combine. Cache the sampled array on disk keyed by grid spec.
   - On failure (or SIMULATE_API_FAILURE=worldcover): return a uniform fallback class (grassland 30) and a ProvenanceRecord with is_stale=True and note "FUEL UNKNOWN - uniform fallback". The caller must add a warning.

3. core/fire/fuel.py: CLASS_NAMES dict and BASE_ROS_M_PER_MIN dict exactly as: 10 tree cover 3.0, 20 shrubland 8.0, 30 grassland 15.0, 40 cropland 10.0, 50 built-up 0.5, 60 bare 0.2, 70 snow 0.0, 80 water 0.0, 90 wetland 1.0, 95 mangroves 2.0, 100 moss 2.0. Function base_ros(fuel_class) -> float32 array (unknown codes get 3.0). Document that these are heuristic model parameters tunable in validation.

4. core/layers.py: build_layers(aoi, res_m=None) -> tuple[Layers, list[ProvenanceRecord], list[str] warnings]. Steps: make_grid, get_elevation, get_fuel_class, base_ros. Warn when fuel is a fallback (FUEL UNKNOWN) or when elevation falls back to flat terrain. This function lives in core/layers.py (NOT core/pipeline.py, which is owned by Person 2 and imports it).

5. scripts/prefetch.py: build layers for an AOI given by CLI args and print timing and provenance (if core/data/osm.py has already been merged by Person 2, also fetch the road graph).

6. tests/unit: slippy-tile math, Terrarium decoding on a procedurally built 2x2 PNG, WorldCover tile id naming for four hemisphere cases, slope sign convention on a synthetic ramp.

Acceptance: `pytest tests/unit -q` passes; `python scripts/prefetch.py --west .. --south .. --east .. --north ..` for the AOI returned by find_active_clusters (or a 0.2 x 0.2 degree forest area you choose) succeeds. Also save a debug PNG per layer (elevation with hillshade, fuel classes) into .cache/debug/ using matplotlib so I can eyeball them. Report grid size, resolution, elevation min/max and the fuel class histogram.
````

### P4: Spread engine (Person 1)
````
Context: EmberRoute (see AGENTS.md). Layers exist (core/layers.build_layers). This task builds the fire spread engine: an anisotropic earliest-arrival (minimum travel time) simulation on the grid. Use Planning mode and show me the plan first. You may only edit core/fire/**, scripts/render_spread.py and tests for them.

Task: implement core/fire/spread.py with

simulate_spread(layers: Layers, wind: WindSeries, ignitions: list[tuple[int,int,float]], params: SpreadParams = SpreadParams()) -> SpreadResult

where ignitions are (row, col, t0_min) and t0_min is minutes relative to now (use 0 for currently burning).

Algorithm (implement exactly, document each formula in comments, units in minutes and metres):
- 8-connected grid; move distance = res_m * sqrt(dr^2 + dc^2); move bearing from core.geo.bearing_deg.
- Priority queue (heapq) of (arrival_min, row, col). arrival initialised to +inf (float32). Settle each cell once. Stop expanding when arrival > params.horizon_min.
- For a move from s to d at current time t: h = min(int(t // 60), H-1) where H = len(wind.speed_ms).
  U_mid = wind.speed_ms[h] * params.midflame; mph = U_mid * 2.237.
  LB = 0.936*exp(0.2566*mph) + 0.461*exp(-0.1548*mph) - 0.397, clipped to [1, params.lb_cap]; e = sqrt(LB^2 - 1)/LB.
  wind_to = (wind.dir_from_deg[h] + 180) % 360; theta = angular difference between move bearing and wind_to; f_dir = (1 - e) / (1 - e*cos(theta)).
  f_moist = clip(1.5 - 1.2*RH[h]/100, 0.3, 1.5).
  base_edge = 0.5*(base_ros[s] + base_ros[d]); if base_ros[d] <= 0.01 the move is blocked.
  ros_head = base_edge * (1 + params.k_wind * U_mid) * f_moist * params.ros_scale.
  g = (elev[d] - elev[s]) / dist; f_slope = clip(exp(3.533 * sign(g) * |g|**1.2), 0.25, 6.0).
  ros_edge = ros_head * f_dir * f_slope; dt = dist / ros_edge; candidate arrival = t + dt.
- Return SpreadResult with arrival_min (inf where unburned), the params, ignitions and runtime_s.
- Precompute per-hour arrays (U_mid, LB, e, wind_to, f_moist) and per-direction constants outside the main loop. Pure NumPy plus heapq first. If a 250 x 250 grid takes longer than 5 s, add an optional numba-jitted version selected automatically when numba is importable, with identical results (test equality to 1e-3 minutes).

Also implement:
- ignitions_from_detections(layers, detections, now_utc) -> list of (row, col, 0.0), mapping detections inside the grid to cells, de-duplicated per cell. Raise a clear ValueError if there are none (the caller decides about scenario mode).
- ignition_from_point(layers, lat, lon) -> list with one (row, col, 0.0) for scenario mode; raise ValueError if the point is outside the grid or on a non-burnable cell (base_ros <= 0.01), with a helpful message.
- burned_mask(result, t_min) -> boolean array of cells with arrival <= t_min.
- stats(result) -> dict with burned area (ha) at 2, 6 and 12 hours, max downwind extent (km) and bearing of the burned-area centroid displacement from the ignition centroid.
- core/fire/baseline.py: isotropic_baseline(layers, ignitions, target_area_ha, horizon_min) that spreads with constant ROS (no wind, slope or fuel variation) and chooses the constant ROS by bisection so the burned area at the horizon matches target_area_ha. Used later for validation.

Also implement core/fire/bands.py: arrival_bands(result, step_min=30) -> list of {"t_min": int, "geometry": GeoJSON-style Polygon or MultiPolygon in lon/lat}. For each t = step_min, 2*step_min, ... up to the horizon: mask = arrival_min <= t; vectorise with rasterio.features.shapes using the affine transform Affine(res_m, 0, x0, 0, -res_m, y0) in the grid's UTM CRS; drop polygons smaller than 4 cells; simplify with tolerance res_m * 0.75 (in metres, before reprojection); reproject to lon/lat with pyproj; round coordinates to 5 decimals. The bands are CUMULATIVE (area burned by t_min), so each band contains the previous one. Skip empty bands. Tests: nesting (band[i] is within band[i+1] for a synthetic arrival field), monotonic area, polygon validity, coordinates in lon/lat order, empty input returns an empty list. This feeds the API's arrival_bands field.

Tests in tests/unit/test_spread.py using procedurally generated synthetic Layers (allowed in tests):
1. Zero wind, flat, uniform fuel: arrival time contours are circular (arrival at equal distances equal within 5%) in the 4 cardinal and 4 diagonal directions.
2. Wind 8 m/s from the west on flat uniform fuel: eastward arrival is clearly earlier than westward arrival at the same distance, and the burned shape is elongated east (ratio of x extent to y extent greater than 1.5).
3. Uphill ramp: fire reaches the up-slope cell earlier than the equidistant down-slope cell.
4. Water barrier column (base_ros 0): cells behind a full-width water band are never burned.
5. Wind shift: wind from the west for the first 2 hours, then from the north: the late front bends south (assert arrival ordering on a defined pair of cells).
6. Determinism: two runs equal.
7. Runtime under 5 s for a 250 x 250 synthetic grid (skip with a marker if running on slow CI).

Also write scripts/render_spread.py that loads real layers for an AOI, builds ignitions from live FIRMS detections (or a scenario point given on the CLI), runs the model with live wind, and saves a PNG with hillshade, arrival-time bands (0-2 h, 2-4 h, 4-8 h, 8-12 h), the ignitions and the wind arrow.

Acceptance: `pytest tests/unit/test_spread.py -q` passes; run scripts/render_spread.py on a real AOI and show me the stats dict and the saved PNG path. State the measured runtime and grid size. Check by eye: the burned area elongates downwind and runs faster uphill. If it does not, fix the cause and do not tune the tests.
````

### P6: Validation harness and calibration (Person 1)
````
Context: EmberRoute (see AGENTS.md). The spread engine (P4) and pipeline (P5) work. This task produces the validation evidence for the judges. Use only real historical data (FIRMS archive and Open-Meteo archive).

You may only edit core/fire/validate.py, scripts/validate_spread.py, docs/validation_events.json, docs/calibrated_params.json, docs/validation.md and docs/figures/.

Task: implement core/fire/validate.py and scripts/validate_spread.py.

Design:
- Events: a list of event dicts defined in a small YAML or JSON file docs/validation_events.json that WE fill in from real FIRMS clusters we find (fields: name, aoi bbox, T0 UTC, note). The script must refuse to run if fewer than 3 events are provided. Do not invent events. Provide a helper command `python scripts/validate_spread.py find-events --days-back 8` that uses find_active_clusters-style logic over the FIRMS archive (area endpoint with a start date; VIIRS_SNPP_NRT for the last 10 days or VIIRS_SNPP_SP for older) to list candidate multi-day fires, printing bbox, dates and detection counts.
- For each event: fetch detections in [T0 - 6 h, T0] as ignitions, historical wind from fetch_wind_history for [T0, T0 + 24 h], build real layers for the AOI, simulate with SpreadParams.
- Future set: FIRMS detections in (T0 + 3 h, T0 + 24 h] inside the AOI. Predicted burned area at time t = cells with arrival <= t dilated by 1 cell (VIIRS pixel is about 375 m). Metric 1: recall = fraction of future detections inside the predicted burned area at their own acquisition time. Metric 2: predicted burned area (ha) at 24 h. Metric 3: bearing difference between the observed and the predicted centroid displacement of the burned region (degrees), if at least 5 future detections exist.
- Baseline: isotropic_baseline matched to the same predicted area at 24 h. Compute the same recall for it. Report the improvement.
- Calibration: grid search k_wind in {0.1, 0.25, 0.4}, midflame in {0.3, 0.5, 0.7}, ros_scale in {0.5, 1.0, 1.5, 2.0} using the FIRST TWO events (maximise mean recall at an area no larger than 3x the observed detection hull area, to prevent trivially huge predictions). Evaluate on the remaining events with the frozen parameters. Write the best parameters to docs/calibrated_params.json and make core/config.py or SpreadParams defaults read it if present.
- Output: docs/validation.md containing a Markdown table with EXACTLY this header row so the API can parse it: | Event | Split | Grid | Future detections | Model recall | Baseline recall | Predicted area (ha) | Bearing error (deg) | (Split is train or test), the calibrated parameters, and an honest limitations section (FIRMS is sparse and lags overpass; recall is not IoU; spotting and suppression are not modelled; only N events). Also save a figure per event (predicted bands plus future detections) in docs/figures/.

Constraints: no synthetic events; no hand-edited numbers in validation.md (the script generates it); deterministic given cached inputs; print the cache provenance of every input used.

Acceptance: show `python scripts/validate_spread.py find-events --days-back 8` output; then after I fill docs/validation_events.json, show the run output and the generated docs/validation.md. If the model does not beat the baseline on held-out events, report that honestly and list the most likely causes, without tuning on the held-out events.
````

### R-P8a: Facts, template briefing and guard (Person 1)
````
Context: EmberRoute (see AGENTS.md). core/pipeline.run_pipeline returns a PipelineResult with plans, metrics, provenance and warnings. This task builds the PURE-PYTHON parts of the briefing system. No LLM calls in this task. You may only edit core/agent/briefing.py, core/agent/guard.py and tests for them.

1. core/agent/briefing.py
   - build_facts(result, diff=None) -> dict[str, str]: fact id to a one-line sentence containing its numbers, at most 25 facts and at most about 1,200 tokens in total (estimate tokens as len(text)/4 and trim the least urgent settlements first). Include: mode and data sources; wind (speed, from-direction as degrees and a compass name, source, is_override); burned area at 2, 6 and 12 hours; downwind bearing; the 8 most urgent settlements (TRAPPED first, then by smallest depart-by) with fire arrival minutes, depart-by minutes and route travel minutes; every TRAPPED and ALREADY_BURNING settlement; the naive-route metric (n_naive_cut of n_threatened, n_rescued_by_replan); data freshness in minutes; every warning (degraded fuel, stale feed, override); diff facts (status changes, depart-by changes of 10 minutes or more, new TRAPPED) when diff is given. Round minutes to integers and areas to 1 decimal, consistently.
   - briefing_messages(facts) -> list of chat messages (system and user) for the LLM: "Write a 5 to 8 sentence operational briefing for a district emergency officer using ONLY the facts provided. After every sentence add the supporting fact ids in square brackets, for example [F3][F7]. Quote numbers exactly as written in the facts. Do not add numbers, place names, causes or advice that are not in the facts. If a settlement is TRAPPED say so plainly." The user message is the facts, one per line as "F3: ...".
   - template_briefing(facts) -> str: deterministic text from templates, containing every TRAPPED settlement and the three most urgent EVACUATE settlements, plus the wind and freshness lines.
   - facts_hash(facts) -> str for caching.

2. core/agent/guard.py
   - verify(text, facts) -> GuardResult(clean_text, text_with_markers, dropped_count, ok). Split into sentences; each sentence must contain at least one [F#] that exists in facts; every number token (integers and decimals, also "N min") must appear in the text of at least one cited fact; every capitalised place name must appear in a cited fact (ignore sentence-initial common words). Remove failing sentences. ok is False if fewer than 2 sentences survive. Strip markers for clean_text.

3. Tests (tests/unit): guard rejects a sentence with an invented number, an uncited sentence, an invented place name and a citation to a missing fact id; accepts a correct sentence; handles decimals and a range such as "30-40 minutes" correctly (document how ranges are handled); template_briefing mentions every TRAPPED settlement; build_facts stays under the token cap with 60 synthetic settlements (synthetic data is allowed in tests only); facts are deterministic for equal input.

Acceptance: `pytest tests/unit -q` passes. Show the output and one example of facts and a template briefing built from a real pipeline result once Person 2's pipeline is merged (until then, from a synthetic result in a test).
````

### P12: README, architecture diagram and docs (Person 1)
````
Context: EmberRoute (see AGENTS.md). Produce the documentation the judges require. Do not change application code. Also write docs/assumptions.md in plain language: assumptions A1-A8 and the heuristic parameter table (WorldCover class to base rate of spread, wind, slope and moisture constants), because the API serves it at /api/assumptions and the UI shows it.

Task: write README.md (clean, scannable) with these sections in order: title and one-line pitch; screenshot placeholders listed in a checklist for us to fill (do not invent screenshots); the problem and who it helps; what EmberRoute does (the 3 key outputs: arrival time, safe route, depart-by deadline); live demo URL and video URL placeholders marked TODO; architecture (embed a Mermaid flowchart that matches the code: data feeds -> data layer with cache and provenance -> grid builder -> spread engine -> evacuation solver and naive baseline -> agent orchestrator (tool calls, retries, change detection, briefing guard) -> FastAPI job API -> React + MapLibre frontend served by the same container); data sources table (name, role, live or static, URL); how the AI and agent are used and the guardrails (the fact-ID citation guard, deterministic fallback), and the LLM chain (Groq primary, Ollama backup, deterministic template) with the token budget from section 4 of the playbook, linking docs/llm_limits.md; the algorithms (spread model equations and the time-dependent Dijkstra, concise, reading like documentation not marketing); validation summary pulled from docs/validation.md (link, do not copy numbers by hand); assumptions and limitations (link to docs/assumptions.md); setup and installation (Python 3.11, venv, pip install -r requirements.txt, .env keys with where to get each, run commands, run tests, run health check, run smoke test, run chaos drill, Docker run, and the frontend setup: Node 20, `cd frontend && npm ci && npm run dev`, linking frontend/README.md written by Person 3); repo structure; compliance statement (real data only, what-if features are labelled, built during the hackathon window, open-source libraries credited); team and licence placeholders. Also docs/architecture.md with the Mermaid diagram and a sequence diagram of one monitoring cycle (feed poll -> change detected -> tools -> plan -> guarded briefing -> UI).

Constraints: every claim in the README must be true of the code as it exists; read the code and tests first and list any mismatch you find in your final message. Do not put performance or accuracy numbers in the README unless they are generated by our scripts; link to the generated files instead.

Acceptance: render check of the Mermaid blocks (syntax valid), all relative links resolve, commands in the README are copy-paste correct (run the install and test commands in a clean venv and show the output).
````

### P13: Final QA and freeze (Person 1)
````
Context: EmberRoute (see AGENTS.md). We are near the deadline. This is a review-only task: do NOT add features.

Task: perform a release-readiness audit and produce docs/RELEASE_CHECK.md.
1. Compliance scan: grep the application code (not tests/) AND frontend/src and frontend/dist (run `npm run check` in frontend/) for hardcoded coordinates lists, JSON fixtures, numpy arrays literals bigger than 10 elements, random data generators, `mock`, `fake`, `dummy`, `sample_data`, and any import from tests/. List findings; fix any violation.
2. Secrets scan: no keys in the repo history or working tree (use git log -p for common key patterns and .env tracking check); confirm GROQ_API_KEY and FIRMS_MAP_KEY appear nowhere in the frontend bundle, the repo or any API response.
3. Run the full test suite, chaos drill, smoke test and health check; paste the outputs into docs/RELEASE_CHECK.md.
4. Verify every UI element listed in prompts F2-F7 exists and works against the deployed Space; run `npm run build:prod` and the Playwright e2e test against the real backend; list any gap.
5. Verify the README commands and links; verify docs/validation.md was generated by the script and matches calibrated_params.json.
6. Dependency pin check: requirements.txt installs in a clean venv and in Docker.
7. List the 10 most likely ways the live demo could fail and a mitigation for each.
Report PASS/FAIL per item. Do not "fix" failures by weakening tests; fix the cause or report it.
````

### 9.2 Person 2 track: evacuation, agent, API, deploy

### P3b: OSM road graph, settlements and shelters (Person 2)
````
Context: EmberRoute (see AGENTS.md). P1 (models, geo, cache, errors) is merged. This task builds the road graph, settlements and shelters from OpenStreetMap, the inputs the evacuation solver needs. No mock data. You may only edit core/data/osm.py and tests for it.

Task:

1. core/data/osm.py
   - get_road_graph(aoi) -> networkx MultiDiGraph from osmnx.graph_from_bbox(bbox=(west, south, east, north), network_type="drive"), projected not required. Keep the largest strongly connected component. Add speeds with osmnx.routing.add_edge_speeds(G, hwy_speeds={...conservative defaults for residential 25, tertiary 35, secondary 45, primary 55, trunk 60, unclassified 30, track 15, service 15}, fallback=30) and then add_edge_travel_times. Cache the graph to disk as graphml (TTL 30 days). Retry on the alternate Overpass endpoint (https://overpass.kumi.systems/api/interpreter) before failing. Honour SIMULATE_API_FAILURE=overpass by raising FeedError at the download step only.
   - get_settlements(aoi, G) -> list[Settlement]: osmnx.features_from_bbox with tags {"place": ["village","hamlet","town","suburb","locality"]}, point or centroid geometry, snap each to the nearest graph node (osmnx.distance.nearest_nodes), drop duplicates that snap to the same node within 300 m, drop unnamed ones, cap at 60 settlements (keep the biggest place types first).
   - get_shelters(aoi) -> list of (name, lat, lon, kind) from tags amenity in school, hospital, community_centre.

2. tests/unit: speed-default mapping, settlement de-duplication and node snapping on a small procedurally built networkx graph (allowed in tests only), and the osmnx 2.x bbox order (left, bottom, right, top). tests/integration (marked, RUN_INTEGRATION=1): download a real small bbox graph and assert it has nodes, edges with travel_time and at least one settlement.

Acceptance: `pytest tests/unit -q` passes; for the AOI returned by find_active_clusters (or a 0.2 x 0.2 degree area with villages) print the number of graph nodes, edges, settlements and shelters and the download time, and save a debug PNG of the road graph with settlements and shelters into .cache/debug/. Show a second run to prove the disk cache works (it should be much faster).
````

### P5: Evacuation solver and fire-blind baseline (Person 2)
````
Context: EmberRoute (see AGENTS.md). Layers (P3) and the spread engine (P4) exist. This task builds the time-dependent evacuation solver. Use Planning mode and show me the plan first. You may only edit core/evac/**, core/pipeline.py and tests for them. Until Person 1's spread engine is merged (about hour 11), develop and test with procedurally generated synthetic arrival grids (tests only); then switch to the real engine.

Task: implement the evac package.

1. core/evac/graph_prep.py
   - annotate_edges(G, spread: SpreadResult, grid: GridSpec, evac: EvacParams) -> G: for each edge compute (a) tt_min = length_m / (speed_kph * evac.speed_factor * 1000/60), and (b) fire_min = minimum of spread.arrival_min sampled along the edge geometry every <= res_m metres (use the edge 'geometry' attribute if present, else the straight line between node coordinates). Samples outside the grid are ignored; if all samples are outside the grid, fire_min = inf. Convert lon/lat samples to grid rc with core.geo.lonlat_to_rc (vectorised).
   - compute_safe_targets(G, spread, grid, shelters, evac) -> dict: burned = arrival_min < inf; dist_to_burn_m = scipy.ndimage.distance_transform_edt(~burned) * res_m; node_fire_min = arrival at the node's cell; a node is a safe target iff it lies inside the grid, node_fire_min is inf and dist_to_burn_m >= evac.safe_dist_m. If the burned mask is empty, every node is safe. Flag shelter nodes (a shelter within 300 m). Return {node_id: {"shelter": name|None}}.

2. core/evac/planner.py
   - earliest_safe_route(G, source_node, depart_min, targets, evac) -> (path_nodes, travel_min) | None. Time-dependent Dijkstra: label = clock time at the node. Relax (u, v, key) only if t_u + tt_min + evac.buffer_min <= fire_min (for parallel edges use the fastest feasible). Stop when a target node is settled, preferring shelter targets only if their arrival time is within 5 minutes of the best non-shelter target. Also forbid starting from a source whose own node_fire_min <= depart_min + buffer.
   - latest_departure(G, source_node, targets, evac, horizon_min) -> float|None: binary search of the largest depart_min in [0, horizon] (1-minute tolerance) for which a route exists; None if infeasible at 0. Add a comment explaining why feasibility is monotone in departure time (all constraints are upper-bound deadlines) and why earliest-arrival labels are therefore optimal.
   - plan_settlements(G, settlements, spread, grid, shelters, evac) -> list[SettlementPlan]. For each settlement: fire_arrival_min = min arrival within a 300 m radius of the settlement point. Status: NOT_THREATENED if inf; ALREADY_BURNING if <= 0; EVACUATE if a route exists at depart 0 (fill route_lonlat from the path using edge geometries, route_travel_min, depart_by_min); otherwise TRAPPED with a note recommending shelter-in-place or airlift.

3. core/evac/naive.py
   - naive_route(G, source_node, targets) -> path using networkx shortest path on tt_min ignoring fire.
   - route_is_cut(G, path, depart_min=0, evac) -> bool: walks the path with the same feasibility rule as the planner and returns True if any edge fails.
   - compare(plans, G, targets, evac) -> metrics dict: n_threatened, n_evacuate, n_trapped, n_already_burning, n_naive_cut (threatened settlements whose naive route is cut), n_rescued_by_replan (naive cut but fire-aware route exists), median_depart_by_min, min_depart_by_min. Also set plan.naive_cut on each plan.

4. Extend core/pipeline.py with run_pipeline(aoi, mode, ignition_point=None, wind_override=None, now=None) -> PipelineResult that executes: fetch detections (LIVE mode) or build the scenario ignition, fetch wind (apply override if given), core.layers.build_layers (Person 1), run spread, get graph/settlements/shelters, annotate, plan, compare, and fill provenance and warnings (stale feeds, fallback fuel, no detections, user overrides). In LIVE mode with zero detections, raise NoActiveFireError (custom) rather than inventing an ignition. Record timings per stage in result.trace.

5. tests/unit/test_evac.py using a procedurally generated small networkx graph and a synthetic arrival grid:
   - Fire cuts the short road at a known time; a longer road survives: planner chooses the long road; naive picks the short road and route_is_cut is True.
   - Departure deadline: leaving at the computed latest_departure succeeds, one minute later fails.
   - Settlement enclosed by fire on all roads: TRAPPED.
   - Settlement far from fire: NOT_THREATENED.
   - Buffer works: increasing buffer_min reduces depart_by by about that amount.

Acceptance: `pytest tests/unit -q` passes; run run_pipeline on a real AOI in LIVE mode (or SCENARIO mode with an ignition near several villages if there are no detections) and print metrics plus the first 5 plans. Also save a PNG showing the arrival bands, roads colored by fire_min, settlements colored by status and the routes. Report how many settlements are EVACUATE, TRAPPED, naive-cut. If everything is NOT_THREATENED, pick a more suitable AOI or ignition point and say so.
````

### P7: Pipeline hardening and smoke test (Person 2)
````
Context: EmberRoute (see AGENTS.md). run_pipeline exists (core/pipeline.py). This task makes it robust and API-ready. No new features. You may only edit core/pipeline.py, core/evac/**, scripts/smoke_pipeline.py and tests for them.

Task:
1. In core/pipeline.py add: input validation (AOI extent limits, ignition inside AOI, wind override ranges: speed 0-40 m/s, direction 0-360), and result caching by an input hash so identical requests within 60 seconds reuse the result.
2. Make every failure path return a structured PipelineError with a user-facing message and a machine code (NO_FIRE, FEED_DOWN, OSM_EMPTY, GRID_TOO_LARGE, NO_SETTLEMENTS, etc.). Add the matching degradations: stale weather allowed with a warning; fallback fuel allowed with a warning; empty OSM graph raises OSM_EMPTY; zero settlements returns a result with a warning and an empty plans list (not an exception).
3. (GeoJSON conversion for the API lives in api/geojson.py, task A1, not here.) Add stage timings and per-stage ProvenanceRecords into result.trace and result.provenance.
4. scripts/smoke_pipeline.py: runs health checks and then run_pipeline in LIVE mode for the auto-selected active cluster, asserts non-empty provenance, finite metrics and that every route polyline has at least 2 points; then runs SCENARIO mode at the AOI centre with a wind override; prints a PASS/FAIL table and total runtime. Exit non-zero on FAIL.
5. Fault-injection tests (tests/integration, marked integration): run the pipeline with SIMULATE_API_FAILURE set to each of open_meteo, worldcover and overpass in turn and assert the documented degradation (warning present, no crash). For firms, assert a FeedError message when there is no cache and a stale flag when a cache exists.

Acceptance: `pytest tests/unit -q` passes; `RUN_INTEGRATION=1 pytest tests/integration -q` passes; `python scripts/smoke_pipeline.py` prints PASS. Show the outputs.
````

### R-P8b: LLM client, tools and orchestrator (Person 2)
````
Context: EmberRoute (see AGENTS.md). run_pipeline works. core/agent/briefing.py and guard.py exist (Person 1). The LLM is Groq (free tier, OpenAI-compatible) with Ollama as a local backup; Gemini is NOT used. The agent must be useful on a tight free-tier token budget. Use Planning mode and show me the plan first. You may only edit core/agent/{llm,tools,orchestrator,trace}.py, scripts/llm_selftest.py and tests for them.

1. core/agent/trace.py: Trace with entries {ts_utc, step, tool, args_summary (short, no secrets), status ok|retry|degraded|error, duration_ms, note}; thread-safe append; to_list(); context manager `with trace.step("run_spread", args=...)` recording timing and exceptions.

2. core/agent/llm.py
   - Use the `openai` package with base_url (OpenAI-compatible). Provider specs come from LLM_CHAIN ("groq:<model>", "ollama:<model>"); groq uses GROQ_BASE_URL and GROQ_API_KEY; ollama uses OLLAMA_BASE_URL with a dummy key. Roles: planner uses LLM_PLANNER_MODEL, briefing uses LLM_BRIEFING_MODEL; each role tries its model first and then the rest of the chain in order.
   - chat(messages, role, tools=None, max_tokens) -> LLMResponse(text, tool_calls, usage (prompt/completion tokens), provider, model, fallback_used bool). Default max_tokens: planner 150, briefing 350. Timeout LLM_TIMEOUT_S, temperature 0.1 for planner and 0.2 for briefing.
   - On HTTP 429: read the retry-after header; if it is 5 s or less wait once, otherwise move to the next entry in the chain immediately. On timeout, 5xx or connection error: next entry. If the chain is exhausted raise LLMUnavailable.
   - Token accounting: a process-wide counter of total tokens used today (from usage fields), logged on every call; when it passes LLM_DAILY_TOKEN_BUDGET raise LLMUnavailable("budget") without calling the API.
   - SIMULATE_API_FAILURE=llm raises LLMUnavailable at call time. Never log keys. Never send arrays, GeoJSON or full tool outputs.
   - is_available() does a cheap check (key present or Ollama reachable) without spending tokens, for the /api/health endpoint.

3. scripts/llm_selftest.py: for every entry in the chain, run (a) a one-line plain completion and (b) a tiny function-calling test (a get_time tool) and print provider, model, latency, token usage and whether the tool call was well-formed. Exit non-zero if no entry passes. Also print the local Ollama model list if reachable and the setup commands: `ollama pull qwen2.5:7b-instruct` or `ollama pull llama3.1:8b`.

4. core/agent/tools.py: plain functions returning small JSON-serialisable dicts: get_fire_detections(aoi), get_weather(center), run_full_plan(aoi, mode, ignition, wind_override), get_settlement_detail(name), expand_search(aoi_scale, horizon_min). Each returns a `summary` that is at most about 300 tokens (use a compact() helper that truncates lists to the top 5 items and rounds numbers); the full PipelineResult is stored in the orchestrator state, not returned to the LLM. Provide TOOL_SCHEMAS (OpenAI function format) with strict types and enums. Tools never raise: they return {"error": code, "message": ...}.

5. core/agent/orchestrator.py: class Orchestrator(settings) with:
   - WorldState: aoi, mode, last_detection_hash, last_wind_summary, last_result, last_run_utc, degraded flags.
   - detect_change(prev, cur) -> reasons: NEW_DETECTIONS, WIND_DIR_SHIFT (circular mean direction over the next 6 h changes by more than 30 degrees; 350 -> 20 is 30 degrees), WIND_SPEED_CHANGE (relative change over 25%), FEED_RECOVERED, MANUAL_REFRESH, OVERRIDE_CHANGED. Pure function.
   - run_cycle(reason) -> CycleResult(result, diff, briefing, trace).
     Planning: LLM tool-calling with the planner role, at most 5 tool calls. System prompt (constant, under about 250 tokens): "You operate a wildfire evacuation planner. Never compute routes or fire arrival yourself; call tools. Default order: get_fire_detections, get_weather, run_full_plan. If a tool returns an error code, choose one recovery: retry once, expand_search, or stop and report. Never invent data. Reply DONE when finished."
     Deterministic fallback: if LLMUnavailable, the model emits an invalid or repeated call, or calls exceed the cap, run the fixed sequence get_fire_detections -> get_weather -> run_full_plan and add a trace entry "LLM unavailable, deterministic planner used".
     Recovery rules in code, independent of the LLM: (a) FEED_DOWN -> retry 3 times with backoff 1, 2, 4 s, then stale cache with a degraded flag; (b) NO_FIRE in LIVE mode -> stop and return NEEDS_SCENARIO and never create an ignition; (c) zero threatened settlements while detections exist -> expand_search once, then report; (d) OSM_EMPTY -> shrink the AOI to 70% once and retry, then report.
     Briefing: build facts (core.agent.briefing), return a cached briefing when facts_hash is unchanged, else call the briefing role with briefing_messages(facts); run guard.verify; if the guard says not ok or the LLM is unavailable use template_briefing and set used_llm False. Record provider, model, dropped_sentences.
   - diff(prev_result, cur_result): status changes, depart_by changes of 10 minutes or more, new TRAPPED, metric deltas.
   - tick(): one poll cycle: fetch feed summaries (no LLM), call detect_change, and run run_cycle only when reasons exist. Returns a TickResult with reasons and the new result if any. The API layer calls tick(); this class starts no threads.

6. Tests (tests/unit) with a fake LLM client class defined in the test file: tool loop success; invalid tool call -> deterministic fallback; 429 with retry-after 2 -> waits once; 429 with retry-after 30 -> next provider; budget exceeded -> no API call; every provider fails -> template briefing; detect_change cases including direction wrap-around; NO_FIRE never creates an ignition; tool summaries stay under the size cap.

Also create docs/llm_limits.md as a template table (provider, model, requests/min, tokens/min, tokens/day, source URL) that the team fills with the real free-tier limits read from the Groq console; do not invent numbers.

Acceptance: `pytest tests/unit -q` passes; `python scripts/llm_selftest.py` passes for at least one provider (show the output with token usage); scripts/agent_demo.py performs one real cycle and prints the trace, the briefing, provider/model used, total tokens spent in the cycle (must be under 6,000) and dropped sentences; then repeat with SIMULATE_API_FAILURE=llm and SIMULATE_API_FAILURE=open_meteo and show the degraded behaviour.
````

### A1: FastAPI layer (Person 2)
````
Context: EmberRoute (see AGENTS.md). core/pipeline.run_pipeline, the Orchestrator and the data layer exist or are being merged. Build the HTTP API that the React frontend will use. You may only edit api/**, tests/api/** and scripts/api_smoke.py. Deliver in the stages v0 (detections, wind, provenance, trace), v1 (+ arrival_bands), v2 (+ settlements, routes, metrics), v3 (+ briefing, monitor, validation); each stage must be usable by itself, with missing parts as empty or absent optional fields.

1. api/schemas.py: pydantic v2 models for every request and response in the contract (endpoints and the PlanResult fields exactly as in section 3 of this document). GeoJSON types as typed dicts. Use Literal enums for status, mode, job status and error codes. Everything optional that is staged. Add examples to the OpenAPI docs.

2. api/main.py: FastAPI app with lifespan; GZipMiddleware (minimum_size 1024); CORS from CORS_ORIGINS for dev; exception handlers mapping PipelineError and validation errors to {error: {code, message}} with proper status codes; mount frontend/dist at "/" with StaticFiles(html=True) when the directory exists, and fall back to a plain JSON message at "/" when it does not; keep /api/* routes registered before the static mount. Run with a single worker (in-memory job store).

3. api/jobs.py: JobManager with a ThreadPoolExecutor(max_workers=2). submit(request) -> job_id; identical input hash within 60 s returns the existing job; jobs expire after 30 minutes; a lock so only 2 pipelines run at once and extra jobs queue. Each job has status, stage (taken from the latest trace step), progress (0-1 from a fixed list of stages), trace (grows while running), result, error. Never block the event loop: heavy work only inside the executor.

4. api/geojson.py: converters from PipelineResult to the contract: detections, settlements, routes (kind aware or naive), naive_cut_segments. Round coordinates to 5 decimals. Use core/fire/bands.py (Person 1) for arrival_bands: cumulative polygons for t_min = 30, 60, ..., horizon, in lon/lat, simplified; if bands.py is not merged yet, return an empty collection and say so in warnings during development only.

5. Endpoints: GET /api/health (core.data.health.check_all plus llm availability), GET /api/clusters, POST /api/plan (202), GET /api/jobs/{id}, POST /api/monitor, GET /api/monitor, GET /api/assumptions (text of docs/assumptions.md), GET /api/validation (parse docs/validation.md table into JSON; return {available: false} if missing).
   Monitor: an asyncio background task started by POST /api/monitor (and cancelled on disable or app shutdown) that calls orchestrator.tick() in the executor every poll_s seconds, updates last_cycle_utc, last_reasons and current_job_id, and stores the new result as a normal job so GET /api/jobs/{id} works for it. Only one monitor at a time.

6. Input validation: AOI limits (0.6 degrees per side, positive extent), ignition inside the AOI, wind override ranges (speed 0-40, direction 0-360), resolution in {60, 90, 120}. Return BAD_INPUT with a helpful message.

7. Security and robustness: no keys in any response; request size limit; rate limit POST /api/plan to 6 per minute per client IP (simple in-memory limiter); structured logging; all external failures become coded errors, never tracebacks.

8. Tests (tests/api) using httpx TestClient with the pipeline function monkeypatched to a fast stub that returns a PipelineResult built procedurally in the test: submit/poll flow, identical-input caching, error mapping for each error code, input validation, monitor enable/disable, gzip header, static mount fallback. Plus scripts/api_smoke.py that runs against a REAL running server: health, clusters, one LIVE or SCENARIO plan, polls to completion, validates the JSON against the pydantic schema, and prints timings.

Acceptance: `pytest tests/api -q` passes; start `uvicorn api.main:app --port 8000` and run scripts/api_smoke.py; show the output and the generated /openapi.json size. Post the final schema summary so Person 3 can generate types.
````

### R-P11: Single-container deploy (Person 2)
````
Context: EmberRoute (see AGENTS.md). The FastAPI backend (api/main.py) and the React frontend (frontend/, built to frontend/dist) exist. Deploy as ONE container to Hugging Face Spaces (Docker SDK). You may only edit Dockerfile, .dockerignore, docs/deploy.md, HF_README_HEADER.md and scripts/smoke_test.py.

1. Multi-stage Dockerfile: stage 1 node:20-slim runs `npm ci && npm run build` in frontend/; stage 2 python:3.11-slim installs requirements.txt (plus the system packages rasterio, shapely and pyproj need, only if the wheels do not work), copies core/, api/, docs/ and the built frontend/dist from stage 1, creates a non-root user, sets CACHE_DIR=/tmp/.cache, exposes 7860 and runs `uvicorn api.main:app --host 0.0.0.0 --port 7860 --workers 1`. Add a HEALTHCHECK against /api/health.
2. HF_README_HEADER.md: Space front matter (sdk: docker, app_port: 7860, title EmberRoute). docs/deploy.md: how to create the Space, set secrets (FIRMS_MAP_KEY, GROQ_API_KEY, LLM_CHAIN, LLM_PLANNER_MODEL, LLM_BRIEFING_MODEL) in the Space settings (never committed), push to the Space repo, and what to click. State that Ollama is NOT available on the free Space: the chain there is Groq, then the template briefing.
3. scripts/smoke_test.py: takes a BASE_URL (default http://localhost:7860), checks /api/health, GET /, runs a real plan through the API, asserts the result schema, measures the total time and prints PASS/FAIL. Used locally against the container and against the deployed Space.
4. Measure the cold start and the first plan time; report both. Make sure the first plan for the default AOI completes in under about 60 s; if not, list what to cache or shrink.
5. Local verification: `docker build -t emberroute .` and `docker run -p 7860:7860 --env-file .env emberroute`, then run the smoke test.

Acceptance: show the build output tail, the container logs of a smoke run and the PASS table. Give me the exact steps to create the Space.
````

### 9.3 Hardening (split between Persons 1 and 2)

### P10: Hardening and edge cases (split: Person 1 data/spread items, Person 2 the rest)
````
Context: EmberRoute (see AGENTS.md). Everything works end to end. This task ONLY hardens behaviour; add no new features. Judges will give unexpected inputs and may have poor network.

Owners: items 1, 2, 3, 6, 9, 10 and 13 belong to Person 1 (data and spread side; edit only Person 1 directories); items 4, 5, 7, 8, 11, 12, 14, 15 and 16-19 plus the chaos drill belong to Person 2. Frontend resilience is covered by F6-F8.

For each case below, write a test (unit where possible, integration otherwise), make the behaviour match, and list the final user-visible message.

1. AOI over open ocean or a desert (no roads, no fuel): clear message, no crash, suggestion to pick another area.
2. AOI larger than allowed or inverted coordinates: validation error with limits.
3. Ignition on water, built-up or bare land: refusal with the reason; ignition outside the grid.
4. No FIRMS detections in the AOI: NEEDS_SCENARIO state.
5. FIRMS or Open-Meteo timeout, HTTP error, HTML error body or malformed JSON: retry, stale cache flagged with age, degraded badge. Without a cache: a clear error, not a traceback.
6. WorldCover or Terrarium tile missing (ocean tile or outage): fallback fuel or flat terrain flagged as DEGRADED. If elevation is unavailable use flat terrain with a prominent warning, and never silently.
7. Overpass slow or empty: alternate endpoint, disk cache, then OSM_EMPTY message.
8. Settlement with no road access, disconnected graph component, or snapped node outside the grid: status NOT_THREATENED or TRAPPED with a note, never an exception.
9. Wind speed 0 (isotropic) and extreme wind (40 m/s) and RH 0 or 100: no NaN or inf in outputs; assert finite arrays.
10. Grid at the AOI edge: fire reaching the grid boundary is reported as "extends beyond the analysed area" in warnings.
11. Rapid repeated clicks on Run: only one pipeline execution at a time; later requests wait or are dropped with a message.
12. Time handling: all internal times UTC, UI shows local (IST) and UTC where useful; detection timestamps parsed correctly around midnight.
13. Memory/time: a 400 x 400 grid completes under 20 s on 2 CPU cores; otherwise automatically coarsen and warn.
14. Secrets: no key ever appears in logs, provenance, traces or the UI (add a test that greps captured logs).
15. LLM output malformed or empty: template briefing used, labelled.

16. Backend unreachable or restarting while a job is running: the job store is in memory, so a lost job id returns a clean JOB_NOT_FOUND error and the UI offers to re-run.
17. Very large GeoJSON payloads: gzip enabled, polygons simplified, coordinates rounded; a plan response over about 5 MB triggers a warning and a coarser band step.
18. Slow or flaky network: all endpoints respond within their timeouts; POST /api/plan returns immediately (202) and never blocks on the pipeline.
19. Page refresh mid-job: the last job id is kept client-side (sessionStorage) and re-fetched; the API keeps finished jobs for 30 minutes.

Add `scripts/chaos_drill.py` that runs the pipeline AND the HTTP API (via httpx against a locally started server) repeatedly under each SIMULATE_API_FAILURE value and a set of bad inputs, and prints a pass/fail table. This script is what we run before every demo.

Acceptance: show the test run and the chaos drill table, all PASS.
````

### 9.4 Person 3 track: frontend

### Design direction (paste into the F1 thread and keep it consistent)
- **Look:** a dark "operations console": a map takes most of the screen, panels float or dock with restrained chrome, and numbers are large and legible. It should look like a tool a district officer would trust, with no marketing gloss.
- **Colour tokens:** background `#0b0f14`, panel `#121821`, border `#1e2733`, text `#e6edf3`, muted text `#8b98a9`, accent (fire) `#ff6a2b`. Status colours: EVACUATE `#2ecc71`, depart-soon (under 60 min) `#f5a524`, TRAPPED `#ff3b30`, ALREADY_BURNING `#8b1a1a` with a white ring, NOT_THREATENED `#6b7787`. Arrival bands: 0-2 h `#ff3b30` alpha .55, 2-4 h `#ff8a00` alpha .5, 4-8 h `#ffc400` alpha .45, 8-12 h `#ffe58a` alpha .4.
- **Typography:** Inter (variable, bundled through `@fontsource-variable/inter`, no CDN) with `tabular-nums` for all numbers; monospace for coordinates and timestamps.
- **Never rely on colour alone:** statuses also carry icons and text labels (colour-blind safe).
- **Semantics on screen:** the mode badge (LIVE / SCENARIO), the WIND OVERRIDE badge, freshness chips (Fires 12 min ago, Weather 4 min ago, STALE in red) and a DEGRADED badge are always visible in the top bar.
- **Basemap:** Carto dark raster tiles `https://{a-d}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png` with the attribution "© OpenStreetMap contributors © CARTO" always shown. Provide the OSM standard tile URL as a fallback if Carto fails.

### F0: Frontend rules (paste as the workspace rules for frontend work)
````
# Frontend rules for EmberRoute (frontend/ only)

You build the web frontend for EmberRoute, a wildfire spread and evacuation planner. You may edit ONLY files under frontend/. The backend (FastAPI) is owned by someone else; its contract is /openapi.json and the types in frontend/src/api/types.ts, which are GENERATED with `npx openapi-typescript <url> -o src/api/types.ts` and never hand-edited.

Stack (do not add others without asking): React 18, TypeScript (strict), Vite, Tailwind CSS, MapLibre GL JS (direct, via a small wrapper component and hooks), TanStack Query for server state, Zustand for UI state, lucide-react for icons, @fontsource-variable/inter for fonts, Vitest + Testing Library for unit tests, Playwright for one end-to-end smoke test.

Data rules (hackathon compliance, strict):
1. No mock, fixture, placeholder or hardcoded domain data anywhere in src/. Every number, place name, status and time shown comes from the API.
2. For development against missing backend fields, use Vitest tests with synthetic props (tests only) and, if needed, a dev-only playground under frontend/dev/ that is excluded from the production build and never imported from src/. Add a script scripts/check-no-fixtures.mjs that fails if dist/ contains the marker string "__DEV_PLAYGROUND__" or any file from frontend/dev/.
3. Empty, loading and error states must be real states driven by the API (not faked).
4. Never log or embed secrets. No third-party scripts or fonts from CDNs (bundle fonts via npm). Map tiles are the only external requests besides /api.

Engineering rules: TypeScript strict, no `any`; components small and typed; map layers built in separate modules under src/map/layers; all colours and spacing from tokens in tailwind config and src/styles/tokens.css; accessible by default (labels, focus states, keyboard operation, aria-live for job progress, status conveyed by icon + text as well as colour); respect prefers-reduced-motion; memoise expensive derived data (sorting, GeoJSON transforms); avoid re-creating map sources on every render (update data with setData).

Every task ends with: files changed, commands to run, the actual output of `npm run typecheck`, `npm run lint`, `npm test` and `npm run build`, and known limitations. Do not expand scope; if the spec is ambiguous choose the simplest option and state it.
````

### F1: Scaffold, design system, app shell, typed API client
````
Context: frontend rules are in the workspace rules. The backend runs on http://localhost:8000 (uvicorn api.main:app) and exposes /openapi.json. Goal: a running shell with real data from /api/health and /api/clusters.

Task:
1. Create frontend/ with Vite + React + TS (strict) + Tailwind; scripts: dev, build, preview, typecheck (tsc --noEmit), lint (eslint), test (vitest run), e2e (playwright test), gen:types (npx openapi-typescript http://localhost:8000/openapi.json -o src/api/types.ts). vite.config.ts: proxy /api to http://localhost:8000 in dev; build output dir dist.
2. Design tokens from the design direction (colours, status colours, band colours, radius, spacing, shadows) in tailwind.config and src/styles/tokens.css; bundle Inter with @fontsource-variable/inter; global dark theme; tabular numbers utility.
3. Typed API layer: src/api/client.ts (fetch wrapper with timeout, JSON parsing, typed {error:{code,message}} -> ApiError class), src/api/hooks.ts with TanStack Query hooks: useHealth (refetch every 30 s), useClusters, useStartPlan (mutation), useJob(jobId) (polling every 1 s while queued/running, then stops; slow down to 2 s after 20 s), useMonitorState (later). Run gen:types now against the live backend and commit the generated file.
4. App shell (src/App.tsx): full-height layout with a top bar (app name, mode badge placeholder, freshness chips from health data, a "System health" button opening a dialog with the per-feed table: ok icon, latency, detail), a main area with the MapView on the left taking most of the width and a right-hand panel column (width about 380 px). Panels are empty placeholders labelled by name for now.
5. MapView (src/map/MapView.tsx): MapLibre map with the Carto dark raster basemap and visible attribution, default view from the first cluster if present, else a world view; navigation controls; a resize observer; exposes a context with the map instance for layer modules.
6. A ClusterList panel: shows real clusters from /api/clusters (lat/lon, detection count, total FRP, relative intensity bar); selecting one flies the map to it and draws the suggested AOI rectangle (a GeoJSON source and line layer). Loading skeleton, error state with retry, empty state ("No active fire clusters found in the last 24 h").
7. Vitest: tests for ApiError mapping, the job polling interval logic and the cluster list states using synthetic props.

Acceptance: with the backend running, `npm run dev` shows the real basemap, real clusters and the real health dialog; typecheck, lint, test and build all pass. Show the outputs and a screenshot description of the result.
````

### F2: Map layers (detections, arrival bands with slider, settlements, routes)
````
Context: F1 is done. The API result type is PlanResult (see src/api/types.ts). Build the map layers and the time slider. Fields arrive in stages: detections first, then arrival_bands, then settlements/routes, so every layer must handle absent or empty fields gracefully.

Task (all under src/map/ and src/state/):
1. src/state/store.ts (Zustand): selectedClusterId, aoi, mode, ignition, windOverride, resolution, jobId, sliderMin, selectedSettlementId, showNaive, layerVisibility. Selectors for derived data (urgency-sorted settlements, current band).
2. Layers as separate modules, each exposing add(map), update(map, data), setVisible(map, visible), remove(map):
   - detectionsLayer: circle layer coloured by FRP (interpolate), radius by zoom, with a hover popup (acquisition time in UTC and local time, FRP, satellite, confidence).
   - arrivalBandsLayer: one GeoJSON source and one fill layer plus a thin outline layer. Sort features by t_min DESCENDING before setData so earlier (more urgent) bands draw on top. Filter `["<=", ["get","t_min"], sliderMin]`. Fill colour by step on t_min using the band colour tokens (0-2 h, 2-4 h, 4-8 h, 8-12 h). A legend component shows the bands.
   - settlementsLayer: circles coloured by status with the icon-and-text rule (use a symbol layer with an icon per status plus a text label for the name); depart-soon amber when EVACUATE and depart_by_min < 60; larger radius and a ring for the selected settlement; popup with arrival time, depart-by, route time, naive-route-cut and the note.
   - routesLayer: aware routes as green lines with a white casing; when showNaive is on, naive routes as dashed grey lines and naive_cut_segments as thick red lines; the selected settlement's route is highlighted and the others dimmed.
   - aoiLayer: AOI rectangle outline; ignitionMarker: a pulsing marker for the scenario ignition (respect reduced motion).
3. TimeSlider component docked at the bottom of the map: range input from 0 to the maximum t_min in the data (step 30 min), label "Fire at +2 h 30 min" plus the wall-clock time in local and UTC, a Play/Pause button that advances in real time at a selectable speed (1x = 1 min per 100 ms... pick sensible 4 speeds), keyboard accessible, and it only appears when arrival_bands has features.
4. Click-to-ignite mode: when mode is SCENARIO and the user is placing an ignition, a map click sets the ignition in the store (cursor changes to a crosshair; Escape cancels). The map never creates an ignition by itself.
5. fitBounds to the AOI when a result arrives; a "Fit to area" button; layer visibility toggles in a small layer control.
6. Tests: pure functions only (band filter expression builder, urgency sort, band sorting, depart-soon rule, time formatting) with synthetic inputs in tests.

Acceptance: against the real backend, show detections on a real plan (v0). When v1 and v2 are available show the bands slider and settlements/routes; until then, verify with the dev-only playground and unit tests and say explicitly which parts were verified how. Typecheck, lint, test and build pass.
````

### F3: Control panel and job flow
````
Context: F1 and F2 are done. Build the control panel and the plan-job flow. The backend contract: POST /api/plan returns {job_id}; GET /api/jobs/{id} returns {status, stage, progress, trace[], result?, error?}.

Task:
1. ControlPanel (src/panels/ControlPanel.tsx) with sections:
   a. Area: tabs "Active fires" (the cluster list from F1) and "Coordinates" (centre lat/lon and size in km, 2-25, with validation messages; draws the AOI rectangle live as you type).
   b. Mode: segmented control "Live detections" / "Scenario ignition". In scenario mode show a "Place ignition on map" button, the chosen coordinates, and a clear button. Show a visible explanation: "Scenario uses real terrain, fuel, roads and weather, with your ignition point."
   c. Wind what-if (collapsed by default): enable switch, speed slider 0-25 m/s with numeric input, direction control (8-point compass buttons plus 0-360 numeric, labelled "wind FROM"). When enabled show a red WIND OVERRIDE (what-if) badge in the top bar.
   d. Resolution select (60, 90, 120 m) with a hint about speed.
   e. Run button: disabled while a job is queued/running or while inputs are invalid; shows the reason when disabled.
2. Job progress: while running, show a stepper or progress bar with the current stage label and a live list of trace entries (aria-live polite); the elapsed time; a cancel-view button (stops polling; it does not need to cancel the server job).
3. Error handling: map error codes to friendly messages with an action: NO_FIRE -> "No active fire detected here. Switch to Scenario mode?" with a one-click switch; FEED_DOWN -> retry button; OSM_EMPTY and GRID_TOO_LARGE -> suggestion to adjust the area; NEEDS_SCENARIO; BAD_INPUT -> show the server message; network failure (backend unreachable) -> a banner with auto-retry. Never show a raw stack trace.
4. TopBar chips: mode badge (LIVE / SCENARIO), WIND OVERRIDE badge, freshness chips computed from provenance fetched_at_utc and re-rendered every 30 s (Fires: 12 min ago, Weather: 4 min ago; red STALE chip if is_stale), a DEGRADED badge whenever warnings or stale flags exist.
5. Tests: input validation functions, error-code mapping, chip age formatting, the disabled-reason logic (synthetic props).

Acceptance: against the real backend run a LIVE plan and a SCENARIO plan end to end (when /api/plan v0 is live), show the progress UI and an error case (a click on an invalid ignition or an AOI over the ocean). Typecheck, lint, test, build pass.
````

### F4: Results: metrics, settlement table, map sync
````
Context: F1-F3 are done. The plan result includes settlements, routes and metrics (stage v2). Build the results panels.

Task:
1. MetricCards (src/panels/Metrics.tsx): five cards: Threatened settlements, Safe route found, Trapped, Naive routes cut by fire, Rescued by re-planning. The "naive routes cut" card is the headline: show "N of M" with a short caption "ordinary shortest routes that fire would cut". Each card has an icon and label, not just colour. Animate number changes briefly (respect reduced motion).
2. SettlementTable (src/panels/SettlementTable.tsx): default sort by urgency (TRAPPED, then ALREADY_BURNING, then smallest depart-by, then NOT_THREATENED last); sortable columns; columns: status (icon + text), name, fire arrival (min, with "h m" tooltip), "Leave within" (depart-by, with a thin urgency bar that shrinks as the deadline nears, amber under 60 min), route time, naive route cut (Yes/No with icon). Row selection syncs to the store (selectedSettlementId) and to the map (fly to the settlement, highlight its route); selecting a marker on the map selects and scrolls to the row. Keyboard operable (arrow keys and Enter). A filter for status. Virtualise rows if there are over 100.
3. SettlementDetail drawer: for the selected settlement show status, arrival time, the leave-by clock time (local and UTC), route travel time, the naive-route comparison (cut or not), the note, and for TRAPPED the recommendation text from the API note field (do not invent advice).
4. "Show fire-blind route" toggle (store.showNaive) in the results header.
5. Empty and partial states: no settlements found; all NOT_THREATENED ("No settlement is threatened within the horizon"); fields not yet available in the API stage (render nothing rather than zeros).
6. Tests: sorting, urgency bar maths, formatting of minutes into "1 h 05 min", the status icon/text mapping and the partial-state rendering (synthetic props).

Acceptance: against the real backend with a v2 result show the metrics, the table, selection syncing with the map and the naive toggle. Typecheck, lint, test and build pass.
````

### F5: Briefing, wind, trace, provenance, validation panels
````
Context: F1-F4 are done. The result includes briefing, wind, provenance, warnings and trace; /api/assumptions and /api/validation exist. Build the explanation and trust panels. These are what convince judges that the data is real and the AI is constrained.

Task:
1. BriefingCard: shows briefing.text as short paragraphs; a label line with provider/model ("Groq / llama-3.3-70b-versatile") or "Template briefing" when used_llm is false; a badge "Verified against solver output" with the dropped_sentences count in a tooltip; an expandable "Facts used" list (briefing.facts) so a judge can audit each number.
2. WindWidget: a compass with an arrow showing the direction the wind blows TO (remember the API gives the FROM direction; convert and label it clearly), the speed, humidity, source and the override/stale flags, and a small SVG sparkline of wind speed over the next 24 h from wind.series.
3. TracePanel: a collapsible "Agent trace" table of trace entries (time, step, tool, status icon, duration, note), the latest on top while running, with a legend; failures and retries are clearly visible.
4. ProvenancePanel: a table of every provenance record (name, source, a link icon to the URL where safe to show, fetched at, age ticking client-side, stale flag, note) plus the warnings list. A prominent line "Live inputs: FIRMS and Open-Meteo fetched at <time>".
5. AssumptionsPanel / About dialog: render /api/assumptions text (assumptions A1-A8 and parameters) with a clear disclaimer: "Decision support. Not a substitute for field command."
6. ValidationPanel: render /api/validation data (table of events with model recall vs baseline recall, a note on limits) or a neutral "Validation results not available" state.
7. Right-column tabs: Results | Briefing | Evidence (trace, provenance, validation, assumptions). The briefing tab opens automatically when a result arrives.
8. Tests: wind direction conversion (from to to, with wrap-around), provenance age formatting, sparkline path generation, the tab state logic (synthetic props).

Acceptance: against the real backend show all panels populated from a real result (briefing when stage v3 is live). Typecheck, lint, test and build pass.
````

### F6: Monitor mode and live behaviour
````
Context: F1-F5 are done. The backend exposes POST /api/monitor ({enabled, aoi, mode, ignition?, wind_override?, poll_s?}) and GET /api/monitor ({enabled, last_cycle_utc, last_reasons[], current_job_id, next_poll_utc}). When the monitor detects a change it runs a new plan as a normal job.

Task:
1. Monitor toggle in the control panel: "Auto-monitor this area" with the poll interval (60 s default, read-only). Enabling posts the current inputs; disabling posts enabled false. Show the status line: last check time, next check countdown, and the last trigger reasons as readable chips (New detections, Wind shift, Wind speed change, Feed recovered, Override changed).
2. Poll GET /api/monitor every 5 s while enabled (pause when the tab is hidden, resume on visibility). When current_job_id changes, fetch that job, replace the displayed result and show a toast "Plan updated: <reasons>".
3. Diff highlighting: compare the previous and new settlements; flash markers and table rows whose status or depart-by changed (depart-by shortened by 10 minutes or more, new TRAPPED), and list the changes in a "What changed" card at the top of the results (for example "Kothagudem: leave within 55 min, was 80 min"). Keep it for 60 s or until dismissed.
4. When the wind override changes while monitoring, send an updated POST /api/monitor and expect an OVERRIDE_CHANGED cycle.
5. Backend unreachable: pause polling, show a banner "Connection lost, retrying" with exponential backoff, resume and re-sync automatically.
6. Tests: diff computation (status change, threshold at 10 minutes, new TRAPPED), polling pause/resume logic, backoff schedule (synthetic props and fake timers).

Acceptance: with the real backend run a monitored session, change the wind override and show the update toast and the diff card. Typecheck, lint, test and build pass.
````

### F7: Responsive layout, accessibility, polish
````
Context: F1-F6 are done. Polish only; do not add features.

Task:
1. Responsive layout: desktop (map plus right column), tablet (right column becomes a collapsible side sheet), mobile (map full screen with a bottom sheet that has three snap points: peek with the key metrics, half, full; the control panel opens as a full-screen sheet). Touch-friendly targets (at least 44 px), no horizontal scroll, the time slider usable on touch.
2. Accessibility: semantic landmarks, labelled controls, visible focus rings, correct tab order, aria-live announcements for job progress and monitor updates, status never conveyed by colour alone, contrast at least 4.5:1 for text against the tokens, reduced-motion support, and a skip link. Run axe through Playwright on the main screens and fix serious violations.
3. States and skeletons: skeleton loaders for panels, empty states with a clear next action, error boundaries around the map and each panel so one failure does not blank the page.
4. Performance: memoise heavy selectors, update map sources with setData and not by re-adding layers, throttle slider updates (use requestAnimationFrame), code-split the validation and about panels, keep the production bundle under about 600 KB gzipped (excluding map tiles) and report the size.
5. Polish: favicon (fire emoji or small SVG), page title and meta description, a compact empty-state hero on first load explaining in one sentence what EmberRoute does and a "Pick an active fire to begin" call to action, consistent spacing and number formatting, a small footer with data attributions (NASA FIRMS, Open-Meteo, OpenStreetMap contributors, ESA WorldCover, AWS Terrain Tiles, Carto).

Acceptance: show screenshots (via Playwright) at 1440, 820 and 390 px widths, the axe report summary and the bundle size. Typecheck, lint, test and build pass.
````

### F8: Integration, end-to-end test, build, screenshots
````
Context: F1-F7 are done and the backend is merged. Final integration and verification of the frontend.

Task:
1. Playwright end-to-end smoke test (e2e/smoke.spec.ts) that runs against a REAL running backend (BASE_URL env var): open the app, wait for the health chips, pick the first cluster (or switch to coordinates), run a plan, wait for completion, assert the metrics cards, the settlement table and map canvas are visible, drag the time slider, toggle the fire-blind route, open the Evidence tab and see the provenance rows, and switch to Scenario mode and place an ignition on the map. The test must tolerate a plan with zero threatened settlements by asserting the empty state. Also an offline test: block /api/** and assert the connection banner.
2. scripts/check-no-fixtures.mjs: fail the build if dist/ contains "__DEV_PLAYGROUND__" or files from frontend/dev/, and if src/ contains imports from frontend/dev or JSON files that look like domain data (any .json larger than 2 KB under src/ except package-like config). Wire it as `npm run check` and into `npm run build:prod` (typecheck, lint, test, build, check).
3. Confirm the production build works behind FastAPI: `npm run build:prod`, then start uvicorn and open http://localhost:8000/, assert the app loads and API calls go to /api on the same origin. Fix base-path issues if any (Vite base must be "/").
4. scripts/screenshots.mjs (Playwright) that captures README and deck screenshots of: initial state, running progress, results with bands at +2 h, settlement detail with the naive toggle, evidence tab, mobile view, into docs/screenshots/ from the REAL app state. Do not fabricate screenshots.
5. Write frontend/README.md: stack, scripts, how to generate types, how to run against the backend, directory structure, and the no-fixtures policy.

Acceptance: show the outputs of `npm run build:prod`, the Playwright run against the real backend and the list of screenshots produced.
````

---

## 10. Demo plan

### 10.1 Pre-demo checklist (run 30 minutes before, and again 10 minutes before)
1. Open the deployed URL to wake the Space; run one full cycle.
2. `python scripts/health_check.py` all green; `python scripts/chaos_drill.py` all PASS; `python scripts/smoke_test.py` against the deployed URL PASS; the System health dialog in the UI is green.
3. Pick the demo AOI (an active FIRMS cluster that has several villages and roads). Note a backup AOI and a scenario ignition point near villages.
4. Close other tabs; phone hotspot ready as a network fallback.
5. Have the repository README, validation.md and the deck open in tabs.

### 10.2 Demo video script (2 min 30 s, screen recording of the LIVE web app, recorded by Person 3)

| Time | Show | Say |
|---|---|---|
| 0:00-0:15 | Title and one sentence | "Fire maps show where it burns. EmberRoute shows when it reaches each village and whether people can still get out." |
| 0:15-0:40 | Pick an active cluster from the cluster list; Evidence tab with real fetch times (provenance) | "Live NASA satellite detections and live wind, fetched seconds ago." |
| 0:40-1:05 | Run the plan; slide the time slider; arrival bands elongate downwind and uphill | "A wind, slope and fuel-aware simulation computes arrival time for every cell." |
| 1:05-1:30 | Settlement table: one EVACUATE with depart-by, one TRAPPED; route on map | "Each village gets a safe route and the latest departure time. This one has no safe road: shelter-in-place or airlift." |
| 1:30-1:50 | Toggle fire-blind route; red cut segment; metric card | "An ordinary shortest route would have been cut by fire for N of M villages." |
| 1:50-2:15 | Turn on the monitor and change the wind override (labelled what-if); the "What changed" card and toast appear; the Evidence tab shows the agent trace with tool calls; briefly set `SIMULATE_API_FAILURE=open_meteo` on the server to show the stale-data banner | "The agent detects the change, calls tools, re-plans, and degrades safely when a feed fails." |
| 2:15-2:30 | Validation number and the guard note | "Validated on N real fires against a naive baseline, and every briefing number is verified against solver output." |

Record it in one take after a dry run. It must be the live app, not a mockup.

### 10.3 Live judging flow
Start from the main page with a pre-warmed AOI. Show provenance first (answers "is this real?"), then the simulation, then the evacuation result, then the agent. Keep the failure drill for the Q&A if asked about robustness.

---

## 11. Submission pack

### 11.1 Form fields
1. **Problem statement:** section 1.1.
2. **Solution description, high-level:** section 1.2.
3. **Technical architecture:** the diagram in section 2.1, the data sources table, the model description in section 5, and the guard description in 5.6. Write it in 6-10 sentences and name the stack: Python, NumPy/SciPy, pyproj, rasterio, osmnx/networkx, FastAPI, React + TypeScript + MapLibre, Groq/Ollama (OpenAI-compatible) function calling.
4. **Prototype link:** Hugging Face Space URL.
5. **Demo video:** Loom or YouTube unlisted link (section 10.2).
6. **GitHub repo:** public, with README, diagram, setup and all source files.
7. **Pitch deck (5-7 slides):** below.

### 11.2 Deck outline (6 slides)
1. **Title and team.** Name, tagline, one visual of arrival bands over a real map.
2. **Problem and context.** Hotspot maps do not give arrival time or a depart-by deadline. State one real fire event and its consequence from a source you can cite.
3. **Solution and key outputs.** Three outputs: arrival time, safe route, depart-by. Screenshot of the settlement table.
4. **Technical architecture and innovation.** The diagram, the time-dependent evacuation solver, the agent loop, the briefing guard, the live and static data feeds.
5. **Proof.** Validation table (generated), naive-vs-aware metric, robustness drill (chaos table).
6. **Roadmap and live demo summary.** Next steps: full Rothermel parameters, spotting model, suppression and firebreaks, SMS/WhatsApp alerts to panchayats, multi-fire, district-scale deployment. Link to the live app.

---

## 12. Edge cases, judge Q&A and risks

### 12.1 Edge-case matrix (what judges may try)

| Input or condition | Expected behaviour |
|---|---|
| Ocean or desert AOI | Clear message, no crash, suggest another area |
| Click on water in scenario mode | Refused with reason |
| No fire detected | Offers scenario mode, never invents an ignition |
| Weather API down | Stale cache with age badge, or clear error |
| FIRMS down with no cache | Clear error, scenario mode still available |
| Zero wind / extreme wind | Finite results, isotropic at zero wind |
| Settlement with no road | Status with note, no exception |
| Huge AOI | Validation message with the limit |
| Double-click Run | Single execution |
| LLM down | Deterministic planner and template briefing, labelled |

### 12.2 Likely judge questions and short answers

| Question | Answer |
|---|---|
| Is the data real? | FIRMS and Open-Meteo are fetched live (provenance panel shows timestamps). Terrain, land cover and roads come from official open datasets at runtime. Scenario and wind overrides are labelled what-ifs on real terrain and roads. |
| How accurate is the spread model? | Show validation.md: recall of future FIRMS detections against an area-matched isotropic baseline, parameters fitted on two events and tested on a held-out one. State the limits: sparse detections, no spotting, simplified physics. |
| Why not just ask an LLM? | The simulator and the solver compute. The agent chooses tools, recovers from failures and explains. A guard rejects any briefing sentence whose numbers are not in the solver output. |
| Walk me through the evacuation solver. | Earliest-arrival Dijkstra where an edge is usable only if the traveller exits it before fire arrival minus a buffer. Binary search over departure time finds the latest viable departure because feasibility only gets harder with later departure. |
| What happens when a feed fails? | Retry with backoff, use the stale cache with an age badge, mark confidence degraded. Demonstrate with the failure flag. |
| How does it scale? | Region-agnostic: any AOI where FIRMS, Open-Meteo, WorldCover, Terrarium and OSM exist. Grid size is capped. Roadmap: tiled runs for districts. |
| What did you build during the hackathon? | Everything under core/, app/ and scripts/. Open-source libraries only for numerics, geodata and UI. |
| Biggest limitation? | Simplified fire physics and sparse detection data. It supports decisions and does not replace field command. |
| Why Groq and Ollama? | Free OpenAI-compatible APIs. Groq is fast and hosted. Ollama runs locally with no token limit. If both are unavailable the system still works through the deterministic planner and a template briefing. |
| What does the LLM actually do? | Chooses which tool to call next from a short list and writes the briefing from a numbered fact list. The guard rejects any sentence whose numbers or names are not in the cited facts. |
| Why a separate frontend? | The simulation is a service. The API returns GeoJSON, so any client (web, SMS bot, dashboard) can use it. |

### 12.3 Risks and scope control

#### Risk register

| Risk | Likelihood | Mitigation |
|---|---|---|
| FIRMS key delayed or rate-limited | Medium | Register before kickoff; cache; scenario mode on real layers |
| No interesting live fire near villages at demo time | Medium | Auto-detect scans the whole world; have 2 backup AOIs; scenario mode |
| Overpass slow | High | Alternate endpoint, disk cache of graph, small bbox, prefetch the demo AOI |
| WorldCover COG reads slow | Medium | Window reads only, cache sampled array |
| Spread model looks wrong | Medium | Gate G3 with the synthetic spread tests first; fix before building on top |
| Validation does not beat baseline | Medium | Report honestly; improve parameters on train events only; explain limits |
| Space cold start or sleep | High | Open early, warm-up, keep a local run as backup |
| Frontend/API contract drift | Medium | Contract freeze at hour 3, additive changes only, generated TS types, staged delivery of real fields |
| Groq free-tier rate limit or outage | Medium | Provider chain to Ollama then template, token budget, briefing cache, SIMULATE_API_FAILURE=llm drill |
| Person 2 overloaded | High | Cut list in 12.4; Person 1 absorbs the validation endpoint and data-side hardening after hour 14 |
| Merge conflicts between three Antigravity agents | Medium | Directory ownership, PR at each milestone, pull main before each prompt |
| Antigravity produces mock data or overreach | Medium | Rules file, plan review, P13 compliance scan |
| Team cannot explain code | Medium | Explain-back after every prompt, section 13 drills |

### 12.4 If you are behind schedule
Cut in this order: third validation event, shelter preference, multi-source detections (NOAA-20), numba, Playwright axe checks, the Ollama provider (keep Groq plus template), LLM tool-planning (keep the deterministic orchestrator plus guarded LLM briefing), the monitor endpoint and F6 (keep manual Run plus the wind override).

### 12.5 Never cut
Real live feeds, arrival-time simulation, time-dependent evacuation solver, naive-vs-aware metric, provenance panel, deployment, chaos drill, README with architecture diagram, the frozen API contract, and the single deployed URL.

---

## 13. Understanding checklist (every team member, before judging)

**Data and grid**
1. Why does Open-Meteo wind direction need a 180 degree flip?
2. How do you decode a Terrarium pixel into metres?
3. Why is the grid in UTM instead of lat/lon?

**Spread model**
4. Why is Dijkstra valid for fire arrival times? (Earliest arrival, costs positive.)
5. What does the length-to-breadth ratio do, and what happens at zero wind?
6. How does a wind shift mid-simulation enter the model?
7. Which effects does it ignore and why does that matter? (Spotting, firebreaks, suppression.)

**Evacuation**
8. When is a road edge usable? Why is the rule conservative?
9. Why does binary search on departure time work?
10. How is `TRAPPED` decided and what do we recommend?
11. What exactly is the naive baseline and why is the comparison fair?

**Agent and AI**
12. What can the LLM decide and what can it never do?
13. How does the guard check a sentence? What happens if the LLM fails?
14. Which triggers cause a re-plan, and why not poll-and-recompute every cycle?

**Validation**
15. What does recall measure here, and why is it not IoU?
16. Which events trained the parameters and which were held out?

Run a 20-minute mock Q&A where teammates ask each other these questions with the code open.

**API and deployment (Person 2)**
17. Why a single uvicorn worker, and what is lost on restart?
18. Walk through the job flow from POST /api/plan to the result, including the cache by input hash.
19. What does the LLM chain do on a 429, a timeout and an exhausted token budget?

**Frontend (Person 3, conceptual)**
1. What does the colour of an arrival band mean, and why are the bands cumulative?
2. What is "Leave within", and why can it be "no safe route"?
3. What is the difference between LIVE and SCENARIO, and what on screen tells a judge which one they are looking at?
4. Why does the API return the wind FROM direction, and how does the compass show it?
5. Walk the path from clicking Run to the polygons on the map: request, job, polling, result, layers.
6. What happens in the UI when the weather feed is down?


---

## 14. Final submission checklist
- [ ] Repo public, README complete with Mermaid diagram, setup steps verified in a clean environment
- [ ] Space live; URL opens without login; health panel green
- [ ] Demo video link works and shows the live app end to end
- [ ] Deck has 6 slides and the validation and robustness proof
- [ ] `docs/validation.md` and `docs/RELEASE_CHECK.md` generated by scripts and committed
- [ ] No keys in the repo; `.env.example` only
- [ ] Commit history starts after kickoff
- [ ] Every member has passed the section 13 drill
- [ ] The Space URL serves the frontend at `/` and the API at `/api`; the System health dialog is green
- [ ] `npm run build:prod` (typecheck, lint, test, build, fixture check) passes; Playwright e2e passes against the real backend
- [ ] Groq and FIRMS keys exist only in Space secrets and local `.env`
- [ ] `docs/llm_limits.md` filled with real numbers from the Groq console

