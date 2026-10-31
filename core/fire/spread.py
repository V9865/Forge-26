"""Wildfire spread simulation engine for EmberRoute.

Implements an anisotropic minimum travel-time earliest-arrival simulation across an 8-connected grid.
Incorporates:
- Hourly wind and relative humidity adjustments (Alexander & Rothermel elliptical formulation)
- McArthur exponential topographic slope acceleration and retardation
- Fuel interface averaging and non-burnable barrier enforcement
All units are explicitly defined: distance in metres, time in minutes, speed in m/min or m/s, bearings in degrees clockwise from North.
"""

from datetime import datetime
import heapq
import logging
import math
import time
from typing import Any, Dict, List, Optional, Tuple
import numpy as np

from core.geo import bearing_deg, haversine_m, lonlat_to_rc, rc_to_lonlat
from core.models import FireDetection, Layers, SpreadParams, SpreadResult, WindSeries

logger = logging.getLogger(__name__)

# 8-connected neighbor offsets: (dr, dc)
NEIGHBOR_OFFSETS = [
    (-1, 0),   # North
    (-1, 1),   # North-East
    (0, 1),    # East
    (1, 1),    # South-East
    (1, 0),    # South
    (1, -1),   # South-West
    (0, -1),   # West
    (-1, -1),  # North-West
]


def _precompute_weather_hours(
    wind: WindSeries, params: SpreadParams
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Precompute hourly weather factors for fast lookup during simulation.

    Args:
        wind: Chronological hourly meteorological series.
        params: Fire spread simulation parameters.

    Returns:
        Tuple of (U_mid, LB, e, wind_to, f_moist) arrays for each hour.
    """
    H = len(wind.speed_ms)
    U_mid = np.zeros(H, dtype=np.float64)
    LB = np.zeros(H, dtype=np.float64)
    e = np.zeros(H, dtype=np.float64)
    wind_to = np.zeros(H, dtype=np.float64)
    f_moist = np.zeros(H, dtype=np.float64)

    for h in range(H):
        # 1. Mid-flame wind speed in m/s
        u_m = float(wind.speed_ms[h]) * float(params.midflame)
        U_mid[h] = u_m

        # 2. Length-to-breadth ratio (Alexander 1985 / Rothermel 1991)
        mph = u_m * 2.237
        lb_val = 0.936 * math.exp(0.2566 * mph) + 0.461 * math.exp(-0.1548 * mph) - 0.397
        lb_clamped = min(float(params.lb_cap), max(1.0, lb_val))
        LB[h] = lb_clamped

        # 3. Ellipse eccentricity: e = sqrt(LB^2 - 1) / LB
        if lb_clamped > 1.0:
            e[h] = math.sqrt(lb_clamped**2 - 1.0) / lb_clamped
        else:
            e[h] = 0.0

        # 4. Heading toward which the wind pushes the fire (degrees clockwise from North)
        wind_to[h] = (float(wind.dir_from_deg[h]) + 180.0) % 360.0

        # 5. Fuel moisture damping factor
        rh_val = float(wind.rh[h]) if h < len(wind.rh) else 30.0
        f_moist[h] = min(1.5, max(0.3, 1.5 - 1.2 * (rh_val / 100.0)))

    return U_mid, LB, e, wind_to, f_moist


def simulate_spread(
    layers: Layers,
    wind: WindSeries,
    ignitions: List[Tuple[int, int, float]],
    params: SpreadParams = SpreadParams(),
) -> SpreadResult:
    """Simulate earliest-arrival fire spread on the 8-connected discrete grid.

    Calculates the minimum travel time isochrone field across all cells using a priority queue.
    Stops expanding once arrival times exceed params.horizon_min.

    Args:
        layers: Spatial layers data structure holding elevation, fuel_class, base_ros, and grid.
        wind: Meteorological hourly observations or forecast series.
        ignitions: List of (row, col, t0_min) starting points where t0_min is relative minutes.
        params: Simulation calibration and physics parameters.

    Returns:
        SpreadResult object containing arrival_min (np.inf for unburned cells), ignitions, and runtime.
    """
    t_start = time.time()

    elev = np.asarray(layers.elevation, dtype=np.float64)
    base_ros = np.asarray(layers.base_ros, dtype=np.float64)
    ny, nx = elev.shape
    res_m = float(layers.grid.res_m)

    # Precompute per-direction move metric distances and compass bearings
    # dr, dc, dist_m, bearing_deg
    neighbor_data = []
    for dr, dc in NEIGHBOR_OFFSETS:
        dist_m = res_m * math.sqrt(dr**2 + dc**2)
        b_deg = float(bearing_deg(dr, dc))
        neighbor_data.append((dr, dc, dist_m, b_deg))

    # Precompute hourly atmospheric parameters
    H = len(wind.speed_ms)
    U_mid, LB, e_arr, wind_to_arr, f_moist_arr = _precompute_weather_hours(wind, params)

    arrival_min = np.full((ny, nx), np.inf, dtype=np.float32)
    settled = np.zeros((ny, nx), dtype=bool)

    pq: List[Tuple[float, int, int]] = []

    # Initialize priority queue with active ignitions
    for r0, c0, t0 in ignitions:
        if 0 <= r0 < ny and 0 <= c0 < nx:
            t0_float = float(t0)
            if t0_float < arrival_min[r0, c0]:
                arrival_min[r0, c0] = t0_float
                heapq.heappush(pq, (t0_float, int(r0), int(c0)))

    horizon_min = float(params.horizon_min)
    k_wind = float(params.k_wind)
    ros_scale = float(params.ros_scale)

    # Dijkstra priority queue expansion
    while pq:
        curr_t, r, c = heapq.heappop(pq)

        if settled[r, c]:
            continue
        settled[r, c] = True

        if curr_t > horizon_min:
            break

        # Hourly index clamped to [0, H-1]
        h = min(int(curr_t // 60), H - 1)
        u_mid_h = U_mid[h]
        e_h = e_arr[h]
        wind_to_h = wind_to_arr[h]
        f_moist_h = f_moist_arr[h]

        r_elev = elev[r, c]
        r_ros = base_ros[r, c]

        # Evaluate 8 connected neighbors
        for dr, dc, dist, bearing in neighbor_data:
            nr = r + dr
            nc = c + dc

            if not (0 <= nr < ny and 0 <= nc < nx):
                continue
            if settled[nr, nc]:
                continue

            base_d = base_ros[nr, nc]
            if base_d <= 0.01:
                # Non-burnable barrier (water, barren rock, ice)
                continue

            # Fuel interface: arithmetic mean of source and destination base rate-of-spread
            base_edge = 0.5 * (r_ros + base_d)

            # Head fire rate of spread (m/min)
            ros_head = base_edge * (1.0 + k_wind * u_mid_h) * f_moist_h * ros_scale

            # Directional elliptical modifier
            theta = abs(bearing - wind_to_h) % 360.0
            theta_rad = math.radians(min(theta, 360.0 - theta))
            denom = 1.0 - e_h * math.cos(theta_rad)
            f_dir = (1.0 - e_h) / denom if denom > 1e-6 else 1.0

            # Topographic slope gradient factor
            g = (elev[nr, nc] - r_elev) / dist
            sign_g = 1.0 if g > 0.0 else (-1.0 if g < 0.0 else 0.0)
            f_slope = min(6.0, max(0.25, math.exp(3.533 * sign_g * (abs(g)**1.2))))

            # Total effective edge rate of spread in m/min
            ros_edge = ros_head * f_dir * f_slope
            if ros_edge <= 1e-4:
                continue

            # Time to traverse edge in minutes (dist in metres / ros_edge in metres/min)
            dt = dist / ros_edge
            cand_arrival = curr_t + dt

            if cand_arrival < arrival_min[nr, nc]:
                arrival_min[nr, nc] = cand_arrival
                heapq.heappush(pq, (cand_arrival, nr, nc))

    runtime_s = time.time() - t_start

    # Format ignitions as lon/lat points for SpreadResult metadata
    ignitions_lonlat: List[Tuple[float, float]] = []
    for r0, c0, _ in ignitions:
        if 0 <= r0 < ny and 0 <= c0 < nx:
            lon, lat = rc_to_lonlat(layers.grid, r0, c0)
            ignitions_lonlat.append((float(lon), float(lat)))

    return SpreadResult(
        grid=layers.grid,
        arrival_min=arrival_min,
        ignitions=ignitions_lonlat,
        params=params,
        runtime_s=runtime_s,
    )


def ignitions_from_detections(
    layers: Layers,
    detections: List[FireDetection],
    now_utc: Optional[datetime] = None,
) -> List[Tuple[int, int, float]]:
    """Map FIRMS active fire detections into discrete simulation grid cells.

    Args:
        layers: Spatial layers with coordinate grid.
        detections: Satellite fire detection points.
        now_utc: Reference time (unused; currently burning cells receive t0 = 0.0).

    Returns:
        List of unique (row, col, 0.0) active ignition tuples.

    Raises:
        ValueError: If no detections fall inside the simulation domain.
    """
    elev = np.asarray(layers.elevation)
    ny, nx = elev.shape

    cells_set = set()
    for d in detections:
        r_f, c_f = lonlat_to_rc(layers.grid, d.lon, d.lat)
        r = int(round(r_f))
        c = int(round(c_f))
        if 0 <= r < ny and 0 <= c < nx:
            cells_set.add((r, c))

    if not cells_set:
        raise ValueError("No active fire detections fell within the simulation grid boundaries.")

    return [(r, c, 0.0) for r, c in sorted(cells_set)]


def ignition_from_point(
    layers: Layers, lat: float, lon: float
) -> List[Tuple[int, int, float]]:
    """Convert a user-specified scenario point into an ignition cell.

    Args:
        layers: Spatial layers with coordinate grid and base rate-of-spread.
        lat: Latitude in decimal degrees.
        lon: Longitude in decimal degrees.

    Returns:
        List with a single (row, col, 0.0) ignition tuple.

    Raises:
        ValueError: If the coordinate is outside grid bounds or lands on a non-burnable cell.
    """
    elev = np.asarray(layers.elevation)
    ny, nx = elev.shape

    r_f, c_f = lonlat_to_rc(layers.grid, lon, lat)
    r = int(round(r_f))
    c = int(round(c_f))

    if not (0 <= r < ny and 0 <= c < nx):
        raise ValueError(
            f"Ignition point ({lat:.4f}, {lon:.4f}) is outside the simulation grid boundaries."
        )

    base_ros = np.asarray(layers.base_ros)
    if base_ros[r, c] <= 0.01:
        raise ValueError(
            f"Ignition point ({lat:.4f}, {lon:.4f}) is on a non-burnable cell (water/rock, base ROS <= 0.01 m/min)."
        )

    return [(r, c, 0.0)]


def burned_mask(result: SpreadResult, t_min: float) -> np.ndarray:
    """Return a 2D boolean mask of cells burned on or before t_min minutes."""
    return result.arrival_min <= float(t_min)


def stats(result: SpreadResult) -> Dict[str, Any]:
    """Compute summary area metrics, maximum downwind reach, and centroid displacement.

    Args:
        result: Completed SpreadResult simulation output.

    Returns:
        Dict containing burned areas at 2h, 6h, 12h (hectares), max downwind extent (km),
        and bearing of burned centroid displacement from ignition centroid.
    """
    grid = result.grid
    arrival = result.arrival_min
    cell_area_ha = (grid.res_m * grid.res_m) / 10000.0

    area_2h = float(np.sum(arrival <= 120.0) * cell_area_ha)
    area_6h = float(np.sum(arrival <= 360.0) * cell_area_ha)
    area_12h = float(np.sum(arrival <= 720.0) * cell_area_ha)

    burned_cells = np.argwhere(arrival <= result.params.horizon_min)
    if len(burned_cells) == 0:
        return {
            "area_ha_2h": 0.0,
            "area_ha_6h": 0.0,
            "area_ha_12h": 0.0,
            "max_downwind_extent_km": 0.0,
            "centroid_displacement_bearing_deg": 0.0,
        }

    # Centroid of burned cells in (row, col)
    mean_r = float(np.mean(burned_cells[:, 0]))
    mean_c = float(np.mean(burned_cells[:, 1]))
    burned_lon, burned_lat = rc_to_lonlat(grid, mean_r, mean_c)

    # Centroid of ignitions
    if result.ignitions:
        ign_lon = float(np.mean([p[0] for p in result.ignitions]))
        ign_lat = float(np.mean([p[1] for p in result.ignitions]))
    else:
        ign_lon, ign_lat = burned_lon, burned_lat

    # Displacement bearing from ignition to burned centroid
    r_ign_f, c_ign_f = lonlat_to_rc(grid, ign_lon, ign_lat)
    dr = mean_r - r_ign_f
    dc = mean_c - c_ign_f
    disp_bearing = float(bearing_deg(dr, dc)) if (abs(dr) > 1e-4 or abs(dc) > 1e-4) else 0.0

    # Max extent from ignition centroid to any burned cell
    max_dist_m = 0.0
    for r_cell, c_cell in burned_cells:
        c_lon, c_lat = rc_to_lonlat(grid, r_cell, c_cell)
        d_m = haversine_m(ign_lon, ign_lat, c_lon, c_lat)
        if d_m > max_dist_m:
            max_dist_m = d_m

    return {
        "area_ha_2h": round(area_2h, 1),
        "area_ha_6h": round(area_6h, 1),
        "area_ha_12h": round(area_12h, 1),
        "max_downwind_extent_km": round(max_dist_m / 1000.0, 2),
        "centroid_displacement_bearing_deg": round(disp_bearing, 1),
    }
