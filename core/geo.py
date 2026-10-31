"""Geospatial utilities, coordinate transforms, and grid generation for EmberRoute.

Coordinate order convention:
- GeoJSON/shapely: (lon, lat) WGS84
- Raster grids: row 0 is northern edge, col 0 is western edge
- Distance units: metres
- Bearing units: degrees clockwise from North [0, 360)
"""

import logging
import math
from typing import Any, Tuple, Union
import numpy as np
import pyproj

from core.models import AOI, GridSpec

logger = logging.getLogger(__name__)


def utm_epsg_for(lat: float, lon: float) -> int:
    """Determine the UTM WGS84 EPSG code for a given latitude and longitude.

    Args:
        lat: Latitude in degrees (-90 to 90).
        lon: Longitude in degrees (-180 to 180).

    Returns:
        EPSG integer (32601-32660 for Northern Hemisphere, 32701-32760 for Southern).
    """
    zone = int((lon + 180.0) // 6.0) + 1
    zone = max(1, min(60, zone))
    if lat >= 0:
        return 32600 + zone
    return 32700 + zone


def haversine_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """Calculate the great-circle distance between two points in metres.

    Args:
        lon1: Point 1 longitude in degrees.
        lat1: Point 1 latitude in degrees.
        lon2: Point 2 longitude in degrees.
        lat2: Point 2 latitude in degrees.

    Returns:
        Distance in metres.
    """
    r_earth_m = 6_371_000.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_phi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
    )
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(max(0.0, 1.0 - a)))
    return r_earth_m * c


def make_grid(aoi: AOI, res_m: float, max_cells: int) -> GridSpec:
    """Construct a UTM GridSpec covering the AOI, coarsening res_m if cells > max_cells.

    Args:
        aoi: Area of Interest bounding box.
        res_m: Desired cell resolution in metres.
        max_cells: Maximum allowable total cells (nx * ny).

    Returns:
        GridSpec covering the AOI in appropriate UTM projection.
    """
    center_lat, center_lon = aoi.center
    epsg = utm_epsg_for(center_lat, center_lon)

    transformer = pyproj.Transformer.from_crs("EPSG:4326", f"EPSG:{epsg}", always_xy=True)

    # Transform all 4 bounding box corners to projected UTM coordinates
    corners_lonlat = [
        (aoi.west, aoi.south),
        (aoi.east, aoi.south),
        (aoi.west, aoi.north),
        (aoi.east, aoi.north),
    ]
    xs, ys = zip(*[transformer.transform(lon, lat) for lon, lat in corners_lonlat])

    xmin, xmax = min(xs), max(xs)
    ymin, ymax = min(ys), max(ys)

    width_m = xmax - xmin
    height_m = ymax - ymin

    curr_res = float(res_m)
    nx = int(math.ceil(width_m / curr_res))
    ny = int(math.ceil(height_m / curr_res))

    # Automatically coarsen resolution if cell count exceeds max_cells
    while (nx * ny) > max_cells:
        scale = math.sqrt((nx * ny) / float(max_cells)) * 1.02
        curr_res = curr_res * scale
        nx = int(math.ceil(width_m / curr_res))
        ny = int(math.ceil(height_m / curr_res))
        logger.info(
            "Auto-adjusted grid resolution to %.1fm (nx=%d, ny=%d, total=%d <= max=%d)",
            curr_res,
            nx,
            ny,
            nx * ny,
            max_cells,
        )

    # Row 0 is the northern edge (top of grid)
    return GridSpec(
        epsg=epsg,
        x0=xmin,
        y0=ymax,
        res_m=curr_res,
        nx=nx,
        ny=ny,
    )


def cell_centers_lonlat(grid: GridSpec) -> Tuple[np.ndarray, np.ndarray]:
    """Compute WGS84 (lon, lat) coordinates for all cell centers in the grid.

    Args:
        grid: Cartesian grid specification.

    Returns:
        Tuple of (lon_array, lat_array), each of shape (ny, nx).
    """
    c_indices = np.arange(grid.nx)
    r_indices = np.arange(grid.ny)

    x_utm = grid.x0 + (c_indices + 0.5) * grid.res_m
    y_utm = grid.y0 - (r_indices + 0.5) * grid.res_m

    xx, yy = np.meshgrid(x_utm, y_utm)

    inv_transformer = pyproj.Transformer.from_crs(
        f"EPSG:{grid.epsg}", "EPSG:4326", always_xy=True
    )
    lons, lats = inv_transformer.transform(xx, yy)
    return lons, lats


def rc_to_lonlat(grid: GridSpec, r: Any, c: Any) -> Tuple[Any, Any]:
    """Convert grid (row, col) coordinates to WGS84 (lon, lat).

    Args:
        grid: Cartesian grid specification.
        r: Row index or numpy array (0 at northern boundary, increases southward).
        c: Column index or numpy array (0 at western boundary, increases eastward).

    Returns:
        Tuple of (lon, lat) in degrees.
    """
    r_arr = np.asarray(r, dtype=float)
    c_arr = np.asarray(c, dtype=float)

    x = grid.x0 + (c_arr + 0.5) * grid.res_m
    y = grid.y0 - (r_arr + 0.5) * grid.res_m

    inv_transformer = pyproj.Transformer.from_crs(
        f"EPSG:{grid.epsg}", "EPSG:4326", always_xy=True
    )
    lons, lats = inv_transformer.transform(x, y)

    if np.ndim(r) == 0 and np.ndim(c) == 0:
        return float(lons), float(lats)
    return lons, lats


def lonlat_to_rc(grid: GridSpec, lon: Any, lat: Any) -> Tuple[Any, Any]:
    """Convert WGS84 (lon, lat) coordinates to continuous grid (row, col).

    Args:
        grid: Cartesian grid specification.
        lon: Longitude in degrees or numpy array.
        lat: Latitude in degrees or numpy array.

    Returns:
        Tuple of (r, c) row and column coordinates.
    """
    lon_arr = np.asarray(lon, dtype=float)
    lat_arr = np.asarray(lat, dtype=float)

    transformer = pyproj.Transformer.from_crs(
        "EPSG:4326", f"EPSG:{grid.epsg}", always_xy=True
    )
    x, y = transformer.transform(lon_arr, lat_arr)

    c = (x - grid.x0) / grid.res_m - 0.5
    r = (grid.y0 - y) / grid.res_m - 0.5

    if np.ndim(lon) == 0 and np.ndim(lat) == 0:
        return float(r), float(c)
    return r, c


def bearing_deg(dr: Union[float, int], dc: Union[float, int]) -> float:
    """Calculate compass bearing in degrees for a grid step.

    Row increases southward (dr > 0 is South, dr < 0 is North).
    Col increases eastward (dc > 0 is East, dc < 0 is West).

    Args:
        dr: Row delta.
        dc: Column delta.

    Returns:
        Bearing in degrees clockwise from North in range [0, 360).
    """
    # x is eastward (dc), y is northward (-dr)
    angle = math.degrees(math.atan2(float(dc), -float(dr)))
    return (angle + 360.0) % 360.0

