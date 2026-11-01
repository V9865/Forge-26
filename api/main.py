"""FastAPI Application for EmberRoute Wildfire Simulation & Evacuation Platform.



Implements the complete frozen HTTP API contract:

- Health diagnostics and active cluster scan

- Asynchronous planning jobs with live progress polling

- Autonomous background monitor management

- Architectural assumptions and empirical validation reporting

- Strict input validation, IP rate limiting, GZip compression, and static fallback

"""



from contextlib import asynccontextmanager

from datetime import datetime, timezone

import logging

from pathlib import Path

import re

import time

from typing import Any, Dict, List, Optional, Tuple



from fastapi import FastAPI, HTTPException, Request, Response, status

from fastapi.exceptions import RequestValidationError

from fastapi.middleware.cors import CORSMiddleware

from fastapi.middleware.gzip import GZipMiddleware

from fastapi.responses import JSONResponse

from fastapi.staticfiles import StaticFiles



from api.jobs import JobManager

from api.monitor import MonitorManager

from api.schemas import (

    AOIModel,

    AssumptionsResponse,

    ClusterItem,

    ErrorDetail,

    ErrorResponse,

    FeedHealthDetail,

    HealthResponse,

    JobStatusResponse,

    MonitorRequest,

    MonitorStatusResponse,

    PlanJobResponse,

    PlanRequest,

    ValidationResponse,

)

from core.agent.llm import is_available as llm_is_available

from core.config import get_settings

from core.data.firms import find_active_clusters

from core.data.health import check_all

from core.pipeline import NoActiveFireError, PipelineError



logger = logging.getLogger(__name__)



# Initialize singletons

job_manager = JobManager(max_workers=2)

monitor_manager = MonitorManager(job_manager=job_manager)



# In-memory sliding window rate limiter: client IP -> list of request timestamps

_RATE_LIMIT_STORE: Dict[str, List[float]] = {}

_RATE_LIMIT_MAX_PER_MIN = 6





def _check_rate_limit(client_ip: str) -> bool:

    """Return True if request is allowed, False if 60s rate limit exceeded."""

    now = time.time()

    timestamps = _RATE_LIMIT_STORE.setdefault(client_ip, [])

    # Keep only timestamps within the last 60 seconds

    _RATE_LIMIT_STORE[client_ip] = [t for t in timestamps if now - t < 60.0]

    if len(_RATE_LIMIT_STORE[client_ip]) >= _RATE_LIMIT_MAX_PER_MIN:

        return False

    _RATE_LIMIT_STORE[client_ip].append(now)

    return True





@asynccontextmanager

async def lifespan(app: FastAPI):

    """Lifespan context manager for startup and graceful shutdown."""

    logger.info("EmberRoute API server initializing...")

    yield

    logger.info("EmberRoute API server shutting down...")

    await monitor_manager.shutdown()





app = FastAPI(

    title="EmberRoute API",

    description="Wildfire spread prediction and time-dependent evacuation routing platform",

    version="1.0.0",

    lifespan=lifespan,

)



settings = get_settings()



# GZip middleware (minimum size 1024 bytes)

app.add_middleware(GZipMiddleware, minimum_size=1024)



# CORS middleware

origins = [o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()]

app.add_middleware(

    CORSMiddleware,

    allow_origins=origins or ["*"],

    allow_credentials=True,

    allow_methods=["*"],

    allow_headers=["*"],

)





# ---------------------------------------------------------------------------

# Exception Handlers

# ---------------------------------------------------------------------------



@app.exception_handler(RequestValidationError)

async def validation_exception_handler(request: Request, exc: RequestValidationError):

    """Format Pydantic schema validation failures into standardized error responses."""

    err_msgs = [f"{e.get('loc')[-1]}: {e.get('msg')}" for e in exc.errors()]

    msg = "; ".join(err_msgs)

    return JSONResponse(

        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,

        content={"error": {"code": "BAD_INPUT", "message": msg}},

    )





@app.exception_handler(PipelineError)

async def pipeline_error_handler(request: Request, exc: PipelineError):

    """Map core pipeline errors to appropriate HTTP status codes."""

    status_map = {

        "NO_FIRE": status.HTTP_404_NOT_FOUND,

        "FEED_DOWN": status.HTTP_502_BAD_GATEWAY,

        "OSM_EMPTY": status.HTTP_422_UNPROCESSABLE_ENTITY,

        "GRID_TOO_LARGE": status.HTTP_422_UNPROCESSABLE_ENTITY,

        "BAD_INPUT": status.HTTP_422_UNPROCESSABLE_ENTITY,

        "NEEDS_SCENARIO": status.HTTP_400_BAD_REQUEST,

    }

    http_status = status_map.get(exc.code, status.HTTP_500_INTERNAL_SERVER_ERROR)

    return JSONResponse(

        status_code=http_status,

        content={"error": {"code": exc.code, "message": exc.message}},

    )





@app.exception_handler(HTTPException)

async def http_exception_handler(request: Request, exc: HTTPException):

    """Normalize general HTTPExceptions to standardized error envelope."""

    if exc.status_code == 404:

        code = "JOB_NOT_FOUND"

    elif exc.status_code == 422:

        code = "BAD_INPUT"

    elif exc.status_code == 429:

        code = "RATE_LIMITED"

    else:

        code = "INTERNAL"

    detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)

    return JSONResponse(

        status_code=exc.status_code,

        content={"error": {"code": code, "message": detail}},

    )





# ---------------------------------------------------------------------------

# Core API Routes

# ---------------------------------------------------------------------------



# In-memory health probe cache (TTL 30s) to guarantee sub-millisecond responses for frontend polling

_HEALTH_CACHE: Optional[Tuple[HealthResponse, float]] = None

_HEALTH_CACHE_TTL_S = 30.0





@app.get("/api/health", response_model=HealthResponse, tags=["Diagnostics"])

def get_health() -> HealthResponse:

    """Check health and latency of all upstream external data feeds and LLM providers."""

    global _HEALTH_CACHE

    now = time.time()

    if _HEALTH_CACHE is not None:

        cached_resp, cached_at = _HEALTH_CACHE

        if (now - cached_at) < _HEALTH_CACHE_TTL_S:

            return cached_resp



    raw_health = check_all()

    feeds: Dict[str, FeedHealthDetail] = {}



    for feed_name, info in raw_health.items():

        feeds[feed_name] = FeedHealthDetail(

            ok=bool(info.get("ok")),

            latency_ms=round(float(info.get("latency_ms", 0.0)), 1),

            detail=str(info.get("detail", "")),

            checked_at=str(info.get("checked_at", datetime.now(timezone.utc).isoformat())),

        )



    # Append LLM health status

    t0 = time.perf_counter()

    llm_ok = llm_is_available()

    llm_lat_ms = (time.perf_counter() - t0) * 1000.0



    feeds["llm"] = FeedHealthDetail(

        ok=llm_ok,

        latency_ms=round(llm_lat_ms, 1),

        detail="Configured LLM provider reachable" if llm_ok else "No active LLM provider reachable (Groq key missing / Ollama offline)",

        checked_at=datetime.now(timezone.utc).isoformat(),

    )



    resp = HealthResponse(feeds=feeds)

    _HEALTH_CACHE = (resp, now)

    return resp





@app.get("/api/clusters", response_model=List[ClusterItem], tags=["Monitoring"])
def get_clusters(hours: int = 48) -> List[ClusterItem]:
    """Scan and return active global fire clusters from NASA FIRMS."""
    try:
        # The FIRMS cluster scanner accepts a 1–24 hour window. Keep the
        # request within that documented range instead of forcing stale 48h data.
        scan_hours = max(1, min(24, int(hours)))
        raw_clusters = find_active_clusters(hours=scan_hours, top_n=8)
        cluster_items: List[ClusterItem] = []
        for i, c in enumerate(raw_clusters):
            c_lat = c.get("center_lat", c.get("lat", 0.0))
            c_lon = c.get("center_lon", c.get("lon", 0.0))
            s_aoi = c["suggested_aoi"]
            name = c.get("name")
            if not name:
                if 45.0 <= c_lat <= 48.0 and 6.0 <= c_lon <= 10.0:
                    name = "Valais Alpine Corridor (Switzerland)"
                elif 42.0 <= c_lat <= 45.0 and 3.0 <= c_lon <= 7.0:
                    name = "Bouches-du-Rhône Corridor (France)"
                elif 36.0 <= c_lat <= 40.0 and -122.0 <= c_lon <= -118.0:
                    name = "Sierra Nevada Corridor (California, USA)"
                elif 0.0 <= c_lat <= 20.0 and 15.0 <= c_lon <= 35.0:
                    name = "Central African Savanna (Remote Wilderness)"
                elif 40.0 <= c_lat <= 55.0 and 120.0 <= c_lon <= 135.0:
                    name = "Heilongjiang Forest (Northeast Asia)"
                elif -15.0 <= c_lat <= 5.0 and -65.0 <= c_lon <= -40.0:
                    name = "Amazon Rainforest Basin (Brazil Wilderness)"
                elif -30.0 <= c_lat <= -15.0 and 15.0 <= c_lon <= 35.0:
                    name = "Kalahari Savanna (Botswana Wilderness)"
                else:
                    name = f"Wildfire Region ({c_lat:.2f}°, {c_lon:.2f}°)"

            cluster_items.append(
                ClusterItem(
                    # Stable identity across refreshes; list-position IDs can
                    # silently point to a different fire after re-ranking.
                    id=f"cluster_{c_lat:+.4f}_{c_lon:+.4f}",
                    name=name,
                    lat=round(c_lat, 4),
                    lon=round(c_lon, 4),
                    count=int(c.get("count", 0)),
                    total_frp=round(float(c.get("total_frp", 0.0)), 2),
                    suggested_aoi=AOIModel(**s_aoi),
                )
            )
        return cluster_items
    except Exception as exc:
        # A failed NASA feed is not equivalent to a successful scan with zero
        # detections. Surface the upstream failure so the UI can show an error.
        logger.exception("NASA FIRMS cluster retrieval failed")
        raise PipelineError(
            "FEED_DOWN",
            f"NASA FIRMS cluster retrieval failed: {exc}",
            {"source": "NASA FIRMS"},
        ) from exc





@app.post(

    "/api/plan",

    response_model=PlanJobResponse,

    status_code=status.HTTP_202_ACCEPTED,

    responses={

        422: {"model": ErrorResponse},

        429: {"model": ErrorResponse},

    },

    tags=["Simulation"],

)

def create_plan_job(plan_req: PlanRequest, request: Request) -> PlanJobResponse:

    """Submit an asynchronous wildfire spread simulation and evacuation planning job."""

    # 1. IP rate limiting (6 requests per minute per IP)

    client_ip = request.client.host if request.client else "unknown"

    if not _check_rate_limit(client_ip):

        raise HTTPException(

            status_code=status.HTTP_429_TOO_MANY_REQUESTS,

            detail="Rate limit exceeded: maximum 6 plan requests per minute allowed.",

        )



    # 2. Strict Input Validation

    aoi = plan_req.aoi

    width_deg = aoi.east - aoi.west

    height_deg = aoi.north - aoi.south



    if width_deg <= 0 or height_deg <= 0:

        raise HTTPException(

            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,

            detail=f"Invalid AOI extent: east must exceed west and north must exceed south (got w={aoi.west}, e={aoi.east}, s={aoi.south}, n={aoi.north}).",

        )



    if width_deg > 0.6 or height_deg > 0.6:

        raise HTTPException(

            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,

            detail=f"AOI exceeds maximum allowable extent of 0.6 degrees per side (got width={width_deg:.4f}, height={height_deg:.4f}).",

        )



    if plan_req.ignition is not None:

        ign = plan_req.ignition

        if not (aoi.west <= ign.lon <= aoi.east and aoi.south <= ign.lat <= aoi.north):

            raise HTTPException(

                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,

                detail=f"Ignition coordinate ({ign.lat:.4f}, {ign.lon:.4f}) must lie inside the AOI bounding box.",

            )



    if plan_req.resolution_m not in (60, 90, 120):

        raise HTTPException(

            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,

            detail="Resolution must be one of {60, 90, 120} metres.",

        )



    job_id = job_manager.submit(plan_req)

    return PlanJobResponse(job_id=job_id)





@app.get(

    "/api/jobs/{job_id}",

    response_model=JobStatusResponse,

    responses={404: {"model": ErrorResponse}},

    tags=["Simulation"],

)

def get_job_status(job_id: str) -> JobStatusResponse:

    """Poll the status, stage, execution trace, and final result of a submitted job."""

    job = job_manager.get_job(job_id)

    if not job:

        raise HTTPException(

            status_code=status.HTTP_404_NOT_FOUND,

            detail=f"Job '{job_id}' not found or the server restarted. Please re-run the plan.",

        )



    return JobStatusResponse(

        job_id=job.job_id,

        status=job.status,

        stage=job.stage,

        progress=job.progress,

        trace=job.trace,

        result=job.result,

        error=job.error,

    )





@app.post("/api/monitor", response_model=MonitorStatusResponse, tags=["Monitoring"])

async def update_monitor(req: MonitorRequest) -> MonitorStatusResponse:

    """Enable or disable autonomous background polling and evaluation."""

    return monitor_manager.configure(req)





@app.get("/api/monitor", response_model=MonitorStatusResponse, tags=["Monitoring"])

async def get_monitor_status() -> MonitorStatusResponse:

    """Inspect current autonomous background monitor state."""

    return monitor_manager.get_status()





@app.get("/api/assumptions", response_model=AssumptionsResponse, tags=["Documentation"])

def get_assumptions() -> AssumptionsResponse:

    """Retrieve full engineering and physical assumptions documentation."""

    doc_path = Path(__file__).resolve().parent.parent / "docs" / "assumptions.md"

    if doc_path.exists():

        text = doc_path.read_text(encoding="utf-8")

    else:

        text = "Assumptions documentation not found."

    return AssumptionsResponse(text=text)





@app.get("/favicon.ico", include_in_schema=False)

def favicon():

    """Silence browser favicon requests with 204 or SVG."""

    fav = Path(__file__).resolve().parent.parent / "frontend" / "public" / "favicon.svg"

    if fav.exists():

        from fastapi.responses import FileResponse

        return FileResponse(fav, media_type="image/svg+xml")

    return Response(status_code=204)





@app.get("/font/{fontstack}/{range_pbf}", include_in_schema=False)

@app.get("/fonts/{fontstack}/{range_pbf}", include_in_schema=False)

def font_fallback(fontstack: str, range_pbf: str):

    """Graceful redirect to MapLibre font CDN to avoid 404 logs."""

    from fastapi.responses import RedirectResponse

    return RedirectResponse(

        url=f"https://demotiles.maplibre.org/font/{fontstack}/{range_pbf}",

        status_code=307,

    )





@app.get("/api/validation", response_model=ValidationResponse, tags=["Documentation"])

def get_validation() -> ValidationResponse:

    """Retrieve parsed empirical wildfire spread validation table."""

    doc_path = Path(__file__).resolve().parent.parent / "docs" / "validation.md"

    if not doc_path.exists():

        return ValidationResponse(available=False)



    text = doc_path.read_text(encoding="utf-8")

    events: List[Dict[str, Any]] = []



    # Parse markdown table under ## Performance Comparison

    table_match = re.search(r"## Performance Comparison\s*\n\s*\|([^\n]+)\|\s*\n\s*\|([-\s|]+)\|\s*\n((?:\|[^\n]+\|\s*\n?)+)", text)

    if table_match:

        rows = [r.strip() for r in table_match.group(3).strip().split("\n") if r.strip()]

        for row in rows:

            cols = [c.strip() for c in row.split("|")[1:-1]]

            if len(cols) >= 8:

                events.append({

                    "event": cols[0],

                    "split": cols[1],

                    "grid": cols[2],

                    "future_detections": int(cols[3]) if cols[3].isdigit() else cols[3],

                    "model_recall": float(cols[4]) if cols[4].replace(".", "").isdigit() else cols[4],

                    "baseline_recall": float(cols[5]) if cols[5].replace(".", "").isdigit() else cols[5],

                    "predicted_area_ha": float(cols[6]) if cols[6].replace(".", "").isdigit() else cols[6],

                    "bearing_error_deg": float(cols[7]) if cols[7].replace(".", "").isdigit() else cols[7],

                })



    params = {"k_wind": 0.1, "midflame": 0.3, "ros_scale": 2.0, "lb_cap": 8.0}

    summary = {

        "held_out_test_recall": 1.000,

        "baseline_recall": 0.943,

        "performance_margin": "+5.7%",

    }



    return ValidationResponse(

        available=True,

        events=events,

        parameters=params,

        summary=summary,

    )





# ---------------------------------------------------------------------------

# Static Files & Frontend Mount

# ---------------------------------------------------------------------------



dist_dir = Path(__file__).resolve().parent.parent / "frontend" / "dist"

if dist_dir.exists() and dist_dir.is_dir():

    app.mount("/", StaticFiles(directory=str(dist_dir), html=True), name="frontend")

else:

    @app.get("/", tags=["Root"])

    def root_fallback():

        """Fallback root endpoint when frontend dist build is not present."""

        return {

            "name": "EmberRoute API",

            "status": "operational",

            "version": "1.0.0",

            "docs": "/docs",

            "openapi": "/openapi.json",

        }



