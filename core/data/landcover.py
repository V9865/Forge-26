"""ESA WorldCover 10m land cover raster ingestion module.

Queries Cloud-Optimized GeoTIFFs directly from AWS S3 via HTTP range requests.
Extracts windowed land cover classes covering the simulation grid and samples
at cell centres using nearest-neighbour interpolation.
Falls back gracefully with explicit warnings if the upstream feed is interrupted.
"""

from datetime import datetime, timezone
import io
import logging
import math
from typing import List, Set, Tuple
import numpy as np
import rasterio
from rasterio.windows import from_bounds, transform as window_transform

from core.cache import cached_or_fetch
from core.config import get_settings
from core.errors import FeedError
from core.geo import cell_centers_lonlat
from core.models import GridSpec, ProvenanceRecord

logger = logging.getLogger(__name__)

WORLDCOVER_BASE_URL = "https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map"
FALLBACK_FUEL_CLASS = 30  # Grassland
STATIC_TTL_S = 30 * 86400  # 30 days


def worldcover_tile_id(lat: float, lon: float) -> str:
    """Compute the ESA WorldCover 3x3 degree tile identifier for a given latitude and longitude.

    Formula:
        lat0 = floor(lat / 3) * 3
        lon0 = floor(lon / 3) * 3
        tile = [N/S][abs(lat0):02d][E/W][abs(lon0):03d]

    Args:
        lat: Latitude in decimal degrees (-90 to 90).
        lon: Longitude in decimal degrees (-180 to 180).

    Returns:
        Tile string (e.g. 'N36W120', 'S36E150').
    """
    lat0 = int(math.floor(lat / 3.0) * 3)
    lon0 = int(math.floor(lon / 3.0) * 3)

    lat_prefix = "N" if lat0 >= 0 else "S"
    lon_prefix = "E" if lon0 >= 0 else "W"

    return f"{lat_prefix}{abs(lat0):02d}{lon_prefix}{abs(lon0):03d}"


def _sample_from_tile(
    tile_id: str,
    lons: np.ndarray,
    lats: np.ndarray,
    out_classes: np.ndarray,
    sampled_mask: np.ndarray,
) -> None:
    """Read bounding window from single WorldCover GeoTIFF and sample cell centres."""
    settings = get_settings()
    url = f"{WORLDCOVER_BASE_URL}/ESA_WorldCover_10m_2021_v200_{tile_id}_Map.tif"

    # GDAL configuration for fast HTTP range reading without directory scan
    env_kwargs = {
        "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": ".tif",
        "GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR",
        "GDAL_HTTP_TIMEOUT": str(int(settings.HTTP_TIMEOUT_S)),
    }

    with rasterio.Env(**env_kwargs):
        with rasterio.open(url) as src:
            tile_w = src.bounds.left
            tile_e = src.bounds.right
            tile_s = src.bounds.bottom
            tile_n = src.bounds.top

            # Identify points falling within this tile
            in_tile = (
                (lons >= tile_w)
                & (lons <= tile_e)
                & (lats >= tile_s)
                & (lats <= tile_n)
            )

            if not np.any(in_tile):
                return

            sub_lons = lons[in_tile]
            sub_lats = lats[in_tile]

            win_left = max(tile_w, float(np.min(sub_lons)) - 0.005)
            win_right = min(tile_e, float(np.max(sub_lons)) + 0.005)
            win_bottom = max(tile_s, float(np.min(sub_lats)) - 0.005)
            win_top = min(tile_n, float(np.max(sub_lats)) + 0.005)

            win = from_bounds(win_left, win_bottom, win_right, win_top, src.transform)
            arr = src.read(1, window=win)

            wt = window_transform(win, src.transform)
            inv_wt = ~wt

            # Nearest neighbour sampling via inverse affine transform
            c_f, r_f = inv_wt * (sub_lons, sub_lats)
            r_idx = np.clip(np.round(r_f).astype(int), 0, arr.shape[0] - 1)
            c_idx = np.clip(np.round(c_f).astype(int), 0, arr.shape[1] - 1)

            out_classes[in_tile] = arr[r_idx, c_idx]
            sampled_mask[in_tile] = True


def get_fuel_class(grid: GridSpec) -> Tuple[np.ndarray, ProvenanceRecord]:
    """Retrieve uint8 WorldCover land cover class codes sampled onto the simulation grid.

    Queries Cloud-Optimized GeoTIFFs using HTTP range reads for only the needed bounding window.
    If the upstream service is unavailable or SIMULATE_API_FAILURE=worldcover is active,
    returns a uniform grassland fallback (30) with an is_stale=True provenance record.

    Args:
        grid: Cartesian grid specification.

    Returns:
        Tuple of (fuel_class_uint8, ProvenanceRecord).
    """
    settings = get_settings()

    cache_key = f"worldcover:sample:{grid.epsg}:{grid.x0:.1f}:{grid.y0:.1f}:{grid.res_m:.1f}:{grid.nx}:{grid.ny}"

    def _do_fetch() -> Tuple[bytes, str, str]:
        if settings.SIMULATE_API_FAILURE == "worldcover":
            raise FeedError("Simulated WorldCover feed failure", source="ESA WorldCover")

        lons, lats = cell_centers_lonlat(grid)

        # Enumerate all needed 3x3 degree tiles across the footprint
        corners = [
            (float(np.min(lats)), float(np.min(lons))),
            (float(np.max(lats)), float(np.min(lons))),
            (float(np.min(lats)), float(np.max(lons))),
            (float(np.max(lats)), float(np.max(lons))),
        ]
        needed_tiles: Set[str] = {worldcover_tile_id(lat, lon) for lat, lon in corners}

        out_classes = np.zeros((grid.ny, grid.nx), dtype=np.uint8)
        sampled_mask = np.zeros((grid.ny, grid.nx), dtype=bool)

        for tile in needed_tiles:
            try:
                _sample_from_tile(tile, lons, lats, out_classes, sampled_mask)
            except Exception as e:
                logger.warning("Error fetching WorldCover tile %s: %s", tile, e)

        if not np.all(sampled_mask):
            unfilled_count = np.sum(~sampled_mask)
            logger.info("Filling %d unmapped cells with default grassland (30)", unfilled_count)
            out_classes[~sampled_mask] = FALLBACK_FUEL_CLASS

        tile_list_str = ",".join(sorted(needed_tiles))
        url = f"{WORLDCOVER_BASE_URL}/ESA_WorldCover_10m_2021_v200_[{tile_list_str}]_Map.tif"

        buf = io.BytesIO()
        np.save(buf, out_classes)
        return buf.getvalue(), "ESA WorldCover", url

    try:
        content_bytes, prov = cached_or_fetch(
            key=cache_key,
            ttl_s=STATIC_TTL_S,
            fetch_fn=_do_fetch,
            allow_stale=True,
        )

        buf = io.BytesIO(content_bytes)
        fuel_array = np.load(buf).astype(np.uint8)
        return fuel_array, prov

    except Exception as e:
        logger.warning("WorldCover fetch failed, returning uniform fallback: %s", e)
        fallback_array = np.full((grid.ny, grid.nx), FALLBACK_FUEL_CLASS, dtype=np.uint8)
        stale_prov = ProvenanceRecord(
            name=f"worldcover:fallback:{grid.nx}x{grid.ny}",
            source="ESA WorldCover",
            url=WORLDCOVER_BASE_URL,
            fetched_at_utc=datetime.now(timezone.utc),
            ttl_s=STATIC_TTL_S,
            is_stale=True,
            note="FUEL UNKNOWN - uniform fallback",
        )
        return fallback_array, stale_prov
