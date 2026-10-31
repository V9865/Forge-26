"""Cumulative fire arrival isochrone vector band extraction for EmberRoute.

Converts discrete arrival time fields into simplified, smoothed GeoJSON-ready
cumulative arrival polygons in WGS84 coordinates.
"""

from typing import Any, Dict, List
import numpy as np
import pyproj
import rasterio.features
from affine import Affine
from shapely.geometry import MultiPolygon, Polygon, mapping, shape
from shapely.ops import transform as shapely_transform, unary_union

from core.models import SpreadResult


def _round_coords(coords: Any, decimals: int = 5) -> Any:
    """Recursively round coordinate tuples/lists to specified decimal precision."""
    if isinstance(coords, (tuple, list)) and len(coords) > 0:
        if isinstance(coords[0], (int, float)):
            return [round(float(c), decimals) for c in coords]
        return [_round_coords(sub, decimals) for sub in coords]
    return coords


def arrival_bands(result: SpreadResult, step_min: int = 30) -> List[Dict[str, Any]]:
    """Extract cumulative vector arrival isochrone polygons at step_min time intervals.

    For each timestamp t = step_min, 2*step_min, ... up to horizon_min:
    1. Thresholds arrival_min <= t into a binary mask.
    2. Vectorizes raster shapes using UTM affine transformation.
    3. Filters out small noise polygons (< 4 cells area).
    4. Simplifies geometries in metric space (tolerance = res_m * 0.75).
    5. Reprojects to WGS84 (EPSG:4326) and rounds coordinates to 5 decimal places.

    Args:
        result: Completed SpreadResult simulation output.
        step_min: Interval step in minutes between cumulative bands (default 30).

    Returns:
        List of dicts: {"t_min": int, "geometry": {"type": ..., "coordinates": ...}}.
        Returns empty list if no burned cells exist.
    """
    arrival = result.arrival_min
    if not np.any(np.isfinite(arrival)):
        return []

    grid = result.grid
    res_m = float(grid.res_m)
    horizon_min = int(result.params.horizon_min)
    step = max(1, int(step_min))

    # Affine transform: origin (x0, y0) with y increasing downwards (-res_m)
    transform = Affine(res_m, 0.0, float(grid.x0), 0.0, -res_m, float(grid.y0))
    min_area_m2 = 4.0 * (res_m * res_m)

    transformer = pyproj.Transformer.from_crs(
        f"EPSG:{grid.epsg}", "EPSG:4326", always_xy=True
    )

    bands: List[Dict[str, Any]] = []

    for t in range(step, horizon_min + 1, step):
        mask = (arrival <= float(t)).astype(np.uint8)
        if not np.any(mask == 1):
            continue

        # Extract polygons from binary mask
        shapes_gen = rasterio.features.shapes(mask, mask=(mask == 1), transform=transform)
        polys: List[Polygon] = []

        for geom_dict, val in shapes_gen:
            if val == 1:
                poly = shape(geom_dict)
                if poly.is_valid and poly.area >= min_area_m2:
                    polys.append(poly)
                elif not poly.is_valid:
                    cleaned = poly.buffer(0)
                    if cleaned.is_valid and cleaned.area >= min_area_m2:
                        if isinstance(cleaned, (Polygon, MultiPolygon)):
                            polys.append(cleaned)

        if not polys:
            continue

        # Union contiguous and disjoint fire components
        combined_geom = unary_union(polys)
        if combined_geom.is_empty:
            continue

        # Simplify in metric UTM space before reprojection
        simplified_utm = combined_geom.simplify(
            tolerance=res_m * 0.75, preserve_topology=True
        )

        # Reproject from UTM to WGS84 (lon, lat)
        lonlat_geom = shapely_transform(transformer.transform, simplified_utm)
        if not lonlat_geom.is_valid:
            lonlat_geom = lonlat_geom.buffer(0)

        geom_dict = mapping(lonlat_geom)
        geom_dict["coordinates"] = _round_coords(geom_dict["coordinates"], decimals=5)

        bands.append({
            "t_min": int(t),
            "geometry": geom_dict,
        })

    return bands
