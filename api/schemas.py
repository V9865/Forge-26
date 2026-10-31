"""Pydantic v2 schemas for EmberRoute HTTP API contract.

Defines all request, response, GeoJSON, and job models matching the
frozen API contract. Provides OpenAPI documentation examples.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional, Tuple, Union
from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Primitive and Common Enums
# ---------------------------------------------------------------------------

PlanMode = Literal["LIVE", "SCENARIO"]
SettlementStatus = Literal["NOT_THREATENED", "EVACUATE", "TRAPPED", "ALREADY_BURNING"]
JobStatus = Literal["queued", "running", "done", "error"]
ResolutionM = Literal[60, 90, 120]
ErrorCode = Literal[
    "NO_FIRE",
    "FEED_DOWN",
    "OSM_EMPTY",
    "GRID_TOO_LARGE",
    "NO_SETTLEMENTS",
    "BAD_INPUT",
    "NEEDS_SCENARIO",
    "INTERNAL",
]


class ErrorDetail(BaseModel):
    """Structured error payload."""

    code: str = Field(..., description="Machine-readable error identifier")
    message: str = Field(..., description="Human-readable explanation of the issue")


class ErrorResponse(BaseModel):
    """Standardized error response container."""

    error: ErrorDetail


# ---------------------------------------------------------------------------
# Geographic & Physical Spec Models
# ---------------------------------------------------------------------------

class AOIModel(BaseModel):
    """Bounding box Area of Interest in WGS84 coordinates."""

    west: float = Field(..., description="West longitude in decimal degrees", ge=-180.0, le=180.0)
    south: float = Field(..., description="South latitude in decimal degrees", ge=-90.0, le=90.0)
    east: float = Field(..., description="East longitude in decimal degrees", ge=-180.0, le=180.0)
    north: float = Field(..., description="North latitude in decimal degrees", ge=-90.0, le=90.0)

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "west": 7.45,
                "south": 46.20,
                "east": 7.65,
                "north": 46.35,
            }
        }
    )


class IgnitionPoint(BaseModel):
    """Geographic ignition coordinate in WGS84."""

    lat: float = Field(..., description="Ignition latitude", ge=-90.0, le=90.0)
    lon: float = Field(..., description="Ignition longitude", ge=-180.0, le=180.0)


class WindOverrideModel(BaseModel):
    """User-specified wind parameter override for SCENARIO simulations."""

    speed_ms: Optional[float] = Field(None, description="Wind speed in metres/second", ge=0.0, le=40.0)
    dir_from_deg: Optional[float] = Field(None, description="Direction wind blows FROM in degrees [0, 360)", ge=0.0, le=360.0)


class GridModel(BaseModel):
    """Physical simulation raster domain specifications."""

    res_m: Union[int, float] = Field(..., description="Cell resolution in metres")
    nx: int = Field(..., description="Grid width in cell count")
    ny: int = Field(..., description="Grid height in cell count")


# ---------------------------------------------------------------------------
# GeoJSON FeatureCollection Typing
# ---------------------------------------------------------------------------

class GeoJSONFeature(BaseModel):
    """Generic GeoJSON Feature."""

    type: Literal["Feature"] = "Feature"
    geometry: Dict[str, Any] = Field(..., description="GeoJSON geometry object")
    properties: Dict[str, Any] = Field(default_factory=dict, description="Feature attributes")


class GeoJSONFeatureCollection(BaseModel):
    """GeoJSON FeatureCollection container."""

    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: List[GeoJSONFeature] = Field(default_factory=list, description="Array of GeoJSON Features")


# ---------------------------------------------------------------------------
# Meteorological Data Models
# ---------------------------------------------------------------------------

class WindNowModel(BaseModel):
    """Current atmospheric snapshot."""

    speed_ms: float
    dir_from_deg: float
    rh: float


class WindPointModel(BaseModel):
    """Single hourly forecast / observation entry."""

    t_utc: str
    speed_ms: float
    dir_from_deg: float
    rh: float


class WindModel(BaseModel):
    """Wind observation and forecast package."""

    source: str
    is_override: bool
    is_stale: bool
    fetched_at_utc: str
    now: WindNowModel
    series: List[WindPointModel] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Briefing and Provenance Models
# ---------------------------------------------------------------------------

class BriefingModel(BaseModel):
    """Synthesized operational briefing and factual citations."""

    text: str
    used_llm: bool
    provider: Optional[str] = None
    model: Optional[str] = None
    dropped_sentences: int = 0
    facts: Dict[str, str] = Field(default_factory=dict)


class ProvenanceModel(BaseModel):
    """Audit record for a data layer."""

    name: str
    source: str
    url: Optional[str] = None
    fetched_at_utc: str
    age_s: Optional[int] = None
    ttl_s: int
    is_stale: bool
    note: Optional[str] = None


class TraceStepModel(BaseModel):
    """Single stage execution timing and outcome."""

    ts_utc: str
    step: str
    tool: Optional[str] = None
    status: str
    duration_ms: float
    note: Optional[str] = None


# ---------------------------------------------------------------------------
# Result of a Completed Simulation & Evacuation Run (PlanResult)
# ---------------------------------------------------------------------------

class PlanResult(BaseModel):
    """Complete simulation, evacuation, and briefing result."""

    mode: PlanMode
    aoi: AOIModel
    grid: GridModel
    wind: WindModel
    detections: GeoJSONFeatureCollection
    arrival_bands: Optional[GeoJSONFeatureCollection] = None
    settlements: Optional[GeoJSONFeatureCollection] = None
    routes: Optional[GeoJSONFeatureCollection] = None
    naive_cut_segments: Optional[GeoJSONFeatureCollection] = None
    metrics: Dict[str, Any] = Field(default_factory=dict)
    briefing: Optional[BriefingModel] = None
    provenance: List[ProvenanceModel] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    trace: List[TraceStepModel] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Request & Response Envelopes
# ---------------------------------------------------------------------------

class PlanRequest(BaseModel):
    """Request payload to initiate an asynchronous simulation run."""

    aoi: AOIModel
    mode: PlanMode = "LIVE"
    ignition: Optional[IgnitionPoint] = None
    wind_override: Optional[WindOverrideModel] = None
    resolution_m: Optional[ResolutionM] = 90

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "aoi": {
                    "west": 7.45,
                    "south": 46.20,
                    "east": 7.65,
                    "north": 46.35,
                },
                "mode": "SCENARIO",
                "ignition": {"lat": 46.28, "lon": 7.55},
                "wind_override": {"speed_ms": 7.0, "dir_from_deg": 240.0},
                "resolution_m": 90,
            }
        }
    )


class PlanJobResponse(BaseModel):
    """Response returned upon accepting a new planning job (HTTP 202)."""

    job_id: str


class JobStatusResponse(BaseModel):
    """Status and progress response for a polling job."""

    job_id: str
    status: JobStatus
    stage: Optional[str] = None
    progress: float = Field(0.0, ge=0.0, le=1.0)
    trace: List[TraceStepModel] = Field(default_factory=list)
    result: Optional[PlanResult] = None
    error: Optional[ErrorDetail] = None


class MonitorRequest(BaseModel):
    """Command payload to configure or toggle autonomous monitoring."""

    enabled: bool
    aoi: Optional[AOIModel] = None
    mode: Optional[PlanMode] = "LIVE"
    ignition: Optional[IgnitionPoint] = None
    wind_override: Optional[WindOverrideModel] = None
    poll_s: Optional[int] = Field(60, ge=10, le=3600)


class MonitorStatusResponse(BaseModel):
    """Current state of the background evaluation monitor."""

    enabled: bool
    last_cycle_utc: Optional[str] = None
    last_reasons: List[str] = Field(default_factory=list)
    current_job_id: Optional[str] = None
    next_poll_utc: Optional[str] = None


class FeedHealthDetail(BaseModel):
    """Health check diagnostic report for a single external feed."""

    ok: bool
    latency_ms: float
    detail: str
    checked_at: str


class HealthResponse(BaseModel):
    """System health diagnostic response."""

    feeds: Dict[str, FeedHealthDetail]


class ClusterItem(BaseModel):
    """Active wildfire hotspot cluster detected from NASA FIRMS."""

    id: str
    lat: float
    lon: float
    count: int
    total_frp: float
    suggested_aoi: AOIModel


class AssumptionsResponse(BaseModel):
    """Engineering and physical assumptions underpinning EmberRoute."""

    text: str


class ValidationResponse(BaseModel):
    """Empirical spread validation summary."""

    available: bool
    events: List[Dict[str, Any]] = Field(default_factory=list)
    parameters: Dict[str, Any] = Field(default_factory=dict)
    summary: Dict[str, Any] = Field(default_factory=dict)

