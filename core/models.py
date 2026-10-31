"""Domain data models for EmberRoute.

Defines Pydantic v2 models and dataclasses for spatial extents, environmental
observations, fire behavior predictions, and evacuation routing.
Coordinate order:
- GeoJSON/shapely conventions: (lon, lat)
- Explicitly stated (lat, lon) on Settlement, FireDetection, and AOI.center.
"""

from dataclasses import dataclass
from datetime import datetime
import math
from typing import Any, Dict, List, Literal, Optional, Tuple, Union
import numpy as np
from pydantic import BaseModel, ConfigDict, Field, model_validator


def _haversine_km(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """Calculate haversine distance in kilometres."""
    r_earth_km = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_phi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
    )
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(max(0.0, 1.0 - a)))
    return r_earth_km * c


class AOI(BaseModel):
    """Area of Interest bounding box in WGS84 degrees.

    Attributes:
        west: Minimum longitude (-180 to 180).
        south: Minimum latitude (-90 to 90).
        east: Maximum longitude (-180 to 180).
        north: Maximum latitude (-90 to 90).
    """

    west: float
    south: float
    east: float
    north: float

    @model_validator(mode="after")
    def validate_bounds(self) -> "AOI":
        if self.west >= self.east:
            raise ValueError(f"west ({self.west}) must be strictly less than east ({self.east})")
        if self.south >= self.north:
            raise ValueError(f"south ({self.south}) must be strictly less than north ({self.north})")
        if (self.east - self.west) > 0.6:
            raise ValueError(f"AOI width ({self.east - self.west:.4f}°) exceeds maximum allowed 0.6°")
        if (self.north - self.south) > 0.6:
            raise ValueError(f"AOI height ({self.north - self.south:.4f}°) exceeds maximum allowed 0.6°")
        return self

    @property
    def center(self) -> Tuple[float, float]:
        """Return center coordinates as (lat, lon) in degrees."""
        return ((self.south + self.north) / 2.0, (self.west + self.east) / 2.0)

    @property
    def width_km(self) -> float:
        """Width of AOI along mid-latitude in kilometres."""
        mid_lat = (self.south + self.north) / 2.0
        return _haversine_km(self.west, mid_lat, self.east, mid_lat)

    @property
    def height_km(self) -> float:
        """Height of AOI along mid-longitude in kilometres."""
        mid_lon = (self.west + self.east) / 2.0
        return _haversine_km(mid_lon, self.south, mid_lon, self.north)


class GridSpec(BaseModel):
    """Cartesian grid specification for raster computation in UTM coordinates.

    Coordinates:
        epsg: Projected coordinate system EPSG code (e.g. 32610 for UTM zone 10N).
        x0: Top-left/westernmost X coordinate in metres.
        y0: Northernmost Y coordinate in metres (row 0).
        res_m: Grid cell spatial resolution in metres.
        nx: Number of columns (cells West to East).
        ny: Number of rows (cells North to South).
    """

    epsg: int
    x0: float
    y0: float
    res_m: float
    nx: int
    ny: int


class FireDetection(BaseModel):
    """Satellite active fire detection point from NASA FIRMS.

    Coordinates: (lat, lon).
    """

    lat: float
    lon: float
    acq_time_utc: datetime
    frp: float
    confidence: Union[str, float]
    satellite: str


class WindSeries(BaseModel):
    """Chronological hourly wind and weather observations or forecasts."""

    start_utc: datetime
    speed_ms: List[float]
    dir_from_deg: List[float]
    rh: List[float]
    temp_c: List[float]
    source: str
    fetched_at_utc: datetime
    is_override: bool = False
    is_stale: bool = False


class Layers(BaseModel):
    """Consolidated environmental raster grids for simulation."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    grid: GridSpec
    elevation: Any
    fuel_class: Any
    base_ros: Any
    provenance: Dict[str, Any] = Field(default_factory=dict)


class SpreadParams(BaseModel):
    """Parameters controlling Rothermel/cellular fire rate-of-spread."""

    k_wind: float = 0.25
    midflame: float = 0.5
    ros_scale: float = 1.0
    lb_cap: float = 8.0
    horizon_min: int = 720


class SpreadResult(BaseModel):
    """Output of fire arrival time calculation across the domain."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    grid: GridSpec
    arrival_min: np.ndarray
    ignitions: List[Tuple[float, float]] = Field(default_factory=list)
    params: SpreadParams
    runtime_s: float


class Settlement(BaseModel):
    """Populated place, community, or asset within the area of interest."""

    id: str
    name: str
    lat: float
    lon: float
    node: Optional[int] = None


class EvacParams(BaseModel):
    """Evacuation routing safety parameters."""

    speed_factor: float = 0.6
    buffer_min: float = 10.0
    safe_dist_m: float = 1500.0


class SettlementPlan(BaseModel):
    """Evacuation schedule and route recommendation for a specific settlement."""

    settlement: Settlement
    status: Literal["NOT_THREATENED", "EVACUATE", "TRAPPED", "ALREADY_BURNING"]
    fire_arrival_min: Optional[float] = None
    depart_by_min: Optional[float] = None
    route_lonlat: List[Tuple[float, float]] = Field(default_factory=list)
    route_travel_min: Optional[float] = None
    naive_cut: Optional[bool] = None
    note: str = ""


class ProvenanceRecord(BaseModel):
    """Audit record tracking data source, fetch time, and freshness."""

    name: str
    source: str
    url: str
    fetched_at_utc: datetime
    ttl_s: int
    is_stale: bool = False
    note: str = ""


class PipelineResult(BaseModel):
    """Complete output of the EmberRoute pipeline execution."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    aoi: AOI
    mode: Literal["LIVE", "SCENARIO"]
    detections: List[FireDetection]
    wind: WindSeries
    spread: SpreadResult
    plans: List[SettlementPlan]
    metrics: Dict[str, Any] = Field(default_factory=dict)
    provenance: List[ProvenanceRecord] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    trace: List[Dict[str, Any]] = Field(default_factory=list)
