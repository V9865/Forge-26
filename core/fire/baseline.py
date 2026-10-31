"""Isotropic fire spread baseline for model validation and comparative benchmarking.

Simulates homogeneous circular fire growth under constant rate-of-spread (no wind,
no slope, uniform fuel). Solves for the matching baseline rate-of-spread via
bisection search so the total burned area at horizon_min matches target_area_ha.
"""

import heapq
import math
import time
from typing import List, Tuple
import numpy as np

from core.geo import rc_to_lonlat
from core.models import Layers, SpreadParams, SpreadResult

NEIGHBOR_OFFSETS = [
    (-1, 0),
    (-1, 1),
    (0, 1),
    (1, 1),
    (1, 0),
    (1, -1),
    (0, -1),
    (-1, -1),
]


def _compute_grid_distances(
    ny: int, nx: int, res_m: float, ignitions: List[Tuple[int, int, float]]
) -> np.ndarray:
    """Compute 8-connected shortest metric distance (metres) from ignitions to all cells."""
    dist_grid = np.full((ny, nx), np.inf, dtype=np.float64)
    settled = np.zeros((ny, nx), dtype=bool)
    pq: List[Tuple[float, int, int]] = []

    for r0, c0, _ in ignitions:
        if 0 <= r0 < ny and 0 <= c0 < nx:
            dist_grid[r0, c0] = 0.0
            heapq.heappush(pq, (0.0, r0, c0))

    neighbor_steps = [
        (dr, dc, res_m * math.sqrt(dr**2 + dc**2)) for dr, dc in NEIGHBOR_OFFSETS
    ]

    while pq:
        curr_d, r, c = heapq.heappop(pq)
        if settled[r, c]:
            continue
        settled[r, c] = True

        for dr, dc, step_m in neighbor_steps:
            nr = r + dr
            nc = c + dc
            if 0 <= nr < ny and 0 <= nc < nx and not settled[nr, nc]:
                new_d = curr_d + step_m
                if new_d < dist_grid[nr, nc]:
                    dist_grid[nr, nc] = new_d
                    heapq.heappush(pq, (new_d, nr, nc))

    return dist_grid


def isotropic_baseline(
    layers: Layers,
    ignitions: List[Tuple[int, int, float]],
    target_area_ha: float,
    horizon_min: float = 720.0,
) -> Tuple[SpreadResult, float]:
    """Calculate an isotropic baseline fire arrival field matching target burned area.

    Args:
        layers: Simulation domain spatial layers.
        ignitions: Ignition starting cells (r, c, t0_min).
        target_area_ha: Target burned area in hectares to match at horizon_min.
        horizon_min: Target simulation time horizon in minutes (default 720).

    Returns:
        Tuple of (SpreadResult, calibrated_constant_ros_m_per_min).
    """
    t_start = time.time()
    elev = np.asarray(layers.elevation)
    ny, nx = elev.shape
    res_m = float(layers.grid.res_m)
    cell_area_ha = (res_m * res_m) / 10000.0

    # Shortest metric travel distance from ignitions
    dist_m = _compute_grid_distances(ny, nx, res_m, ignitions)

    # Bisection search over uniform ROS in m/min
    low_ros = 0.001
    high_ros = 200.0

    for _ in range(40):
        mid_ros = 0.5 * (low_ros + high_ros)
        arrival_candidate = dist_m / mid_ros
        burned_count = np.sum(arrival_candidate <= horizon_min)
        area_ha = burned_count * cell_area_ha

        if area_ha < target_area_ha:
            low_ros = mid_ros
        else:
            high_ros = mid_ros

    calibrated_ros = 0.5 * (low_ros + high_ros)
    arrival_min = (dist_m / calibrated_ros).astype(np.float32)

    # Format ignitions as lon/lat points for result metadata
    ignitions_lonlat = []
    for r0, c0, _ in ignitions:
        if 0 <= r0 < ny and 0 <= c0 < nx:
            lon, lat = rc_to_lonlat(layers.grid, r0, c0)
            ignitions_lonlat.append((float(lon), float(lat)))

    params = SpreadParams(
        k_wind=0.0,
        midflame=0.0,
        ros_scale=1.0,
        horizon_min=int(horizon_min),
    )

    result = SpreadResult(
        grid=layers.grid,
        arrival_min=arrival_min,
        ignitions=ignitions_lonlat,
        params=params,
        runtime_s=time.time() - t_start,
    )

    return result, float(calibrated_ros)
