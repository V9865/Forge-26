"""AWS Terrarium elevation tile ingestion and topographic slope computation.

Fetches 256x256 Terrarium PNG tiles from AWS S3 public bucket at zoom 12,
mosaics tiles with exact Web-Mercator pixel math, samples elevation onto the
simulation grid via bilinear interpolation, and computes terrain slopes.
"""

from datetime import datetime, timezone
import io
import logging
import math
from typing import List, Tuple
import httpx
import numpy as np
from PIL import Image
from scipy.ndimage import map_coordinates

from core.cache import cached_or_fetch
from core.config import get_settings
from core.errors import FeedError
from core.geo import cell_centers_lonlat
from core.models import GridSpec, ProvenanceRecord

logger = logging.getLogger(__name__)

TERRARIUM_BASE_URL = "https://s3.amazonaws.com/elevation-tiles-prod/terrarium"
ZOOM_LEVEL = 12
TILE_SIZE = 256
STATIC_TTL_S = 30 * 86400  # 30 days


def lon_to_tile_x(lon: float, z: int) -> int:
    """Convert longitude in degrees to slippy-map tile X index at zoom level z."""
    n = 2**z
    x = int(math.floor((lon + 180.0) / 360.0 * n))
    return max(0, min(n - 1, x))


def lat_to_tile_y(lat: float, z: int) -> int:
    """Convert latitude in degrees to slippy-map tile Y index at zoom level z."""
    lat_clamped = max(-85.05112878, min(85.05112878, lat))
    lat_rad = math.radians(lat_clamped)
    n = 2**z
    y = int(
        math.floor(
            (1.0 - math.log(math.tan(lat_rad) + 1.0 / math.cos(lat_rad)) / math.pi)
            / 2.0
            * n
        )
    )
    return max(0, min(n - 1, y))


def decode_terrarium_png(png_bytes: bytes) -> np.ndarray:
    """Decode AWS Terrarium PNG bytes into an elevation array in metres.

    Formula: elevation = (R * 256 + G + B / 256) - 32768.

    Args:
        png_bytes: Raw PNG image binary bytes.

    Returns:
        float32 numpy array of shape (height, width) with elevation in metres.
    """
    img = Image.open(io.BytesIO(png_bytes)).convert("RGB")
    arr = np.asarray(img, dtype=np.float32)
    r = arr[:, :, 0]
    g = arr[:, :, 1]
    b = arr[:, :, 2]
    return (r * 256.0 + g + b / 256.0) - 32768.0


def _fetch_tile(x: int, y: int, z: int = ZOOM_LEVEL) -> Tuple[np.ndarray, ProvenanceRecord]:
    """Download and decode a single Terrarium tile, cached with 30-day TTL."""
    settings = get_settings()
    url = f"{TERRARIUM_BASE_URL}/{z}/{x}/{y}.png"
    cache_key = f"terrarium:tile:{z}:{x}:{y}"

    def _do_fetch() -> Tuple[bytes, str, str]:
        with httpx.Client(timeout=settings.HTTP_TIMEOUT_S) as client:
            resp = client.get(url)
            if resp.status_code != 200:
                raise FeedError(
                    f"HTTP {resp.status_code} fetching Terrarium tile {z}/{x}/{y}",
                    source="AWS Terrarium",
                    url=url,
                )
            return resp.content, "AWS Terrarium", url

    content_bytes, prov = cached_or_fetch(
        key=cache_key,
        ttl_s=STATIC_TTL_S,
        fetch_fn=_do_fetch,
        allow_stale=True,
    )

    tile_elev = decode_terrarium_png(content_bytes)
    return tile_elev, prov


def get_elevation(grid: GridSpec) -> Tuple[np.ndarray, ProvenanceRecord]:
    """Sample terrain elevation in metres on the simulation grid.

    Calculates the lon/lat footprint of the grid with a 1-cell margin,
    downloads and mosaics the necessary zoom-12 Terrarium tiles, and samples
    at grid cell centres using Web-Mercator bilinear interpolation.

    Args:
        grid: Cartesian grid specification.

    Returns:
        Tuple of (elevation_m, ProvenanceRecord) where elevation_m is float32 of shape (ny, nx).
    """
    lons, lats = cell_centers_lonlat(grid)

    # Margin of 1 cell in degrees
    cell_deg_lon = (grid.res_m / 111320.0) * 1.5
    cell_deg_lat = (grid.res_m / 110540.0) * 1.5

    min_lon = float(np.min(lons)) - cell_deg_lon
    max_lon = float(np.max(lons)) + cell_deg_lon
    min_lat = float(np.min(lats)) - cell_deg_lat
    max_lat = float(np.max(lats)) + cell_deg_lat

    z = ZOOM_LEVEL
    x_min_tile = lon_to_tile_x(min_lon, z)
    x_max_tile = lon_to_tile_x(max_lon, z)
    # Slippy map Y increases southward, so max_lat corresponds to min_tile_y
    y_min_tile = lat_to_tile_y(max_lat, z)
    y_max_tile = lat_to_tile_y(min_lat, z)

    nx_tiles = x_max_tile - x_min_tile + 1
    ny_tiles = y_max_tile - y_min_tile + 1

    mosaic = np.zeros((ny_tiles * TILE_SIZE, nx_tiles * TILE_SIZE), dtype=np.float32)
    last_prov = None

    for ty in range(y_min_tile, y_max_tile + 1):
        for tx in range(x_min_tile, x_max_tile + 1):
            tile_data, prov = _fetch_tile(tx, ty, z)
            last_prov = prov
            r0 = (ty - y_min_tile) * TILE_SIZE
            c0 = (tx - x_min_tile) * TILE_SIZE
            mosaic[r0 : r0 + TILE_SIZE, c0 : c0 + TILE_SIZE] = tile_data

    # Exact Web-Mercator continuous pixel coordinates for all cell centres
    n = 2**z
    total_px = n * TILE_SIZE
    cols_px = (lons + 180.0) / 360.0 * total_px - (x_min_tile * TILE_SIZE)

    lats_clamped = np.clip(lats, -85.05112878, 85.05112878)
    lats_rad = np.radians(lats_clamped)
    rows_px = (
        (1.0 - np.log(np.tan(np.pi / 4.0 + lats_rad / 2.0)) / np.pi)
        / 2.0
        * total_px
        - (y_min_tile * TILE_SIZE)
    )

    # Sample mosaic with bilinear interpolation
    coords = np.array([rows_px, cols_px])
    sampled = map_coordinates(mosaic, coords, order=1, mode="nearest").astype(np.float32)

    prov_record = ProvenanceRecord(
        name=f"terrarium:mosaic:{grid.epsg}:{grid.nx}x{grid.ny}",
        source="AWS Terrarium",
        url=f"{TERRARIUM_BASE_URL}/{z}/[{x_min_tile}..{x_max_tile}]/[{y_min_tile}..{y_max_tile}].png",
        fetched_at_utc=last_prov.fetched_at_utc if last_prov else datetime.now(timezone.utc),
        ttl_s=STATIC_TTL_S,
        is_stale=last_prov.is_stale if last_prov else False,
        note=f"Mosaic of {nx_tiles}x{ny_tiles} zoom-12 Terrarium tiles",
    )

    return sampled, prov_record


def compute_slope(
    elevation: np.ndarray, res_m: float
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Compute directional spatial elevation gradients and overall slope in degrees.

    Sign convention:
    - X axis points East: dz_dx is change in elevation per metre eastward.
    - Y axis points South: dz_dy is change in elevation per metre southward (rows increase southward).

    Args:
        elevation: 2D numpy array of elevations in metres.
        res_m: Uniform spatial grid cell resolution in metres.

    Returns:
        Tuple of (dz_dx, dz_dy, slope_deg):
        - dz_dx: Rate of elevation change in eastward direction (m/m).
        - dz_dy: Rate of elevation change in southward direction (m/m).
        - slope_deg: Steepest slope angle in degrees [0, 90].
    """
    gy, gx = np.gradient(elevation, float(res_m), float(res_m))
    dz_dy = gy.astype(np.float32)
    dz_dx = gx.astype(np.float32)
    slope_deg = np.degrees(np.arctan(np.hypot(dz_dx, dz_dy))).astype(np.float32)
    return dz_dx, dz_dy, slope_deg
