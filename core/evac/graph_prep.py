"""Graph preparation and spatial annotation module for evacuation routing.

Enriches the road network graph with:
1. Time-dependent edge travel times (minutes) scaled by evac.speed_factor.
2. Fire arrival times (minutes) along road geometries sampled every <= grid.res_m.
3. Safe evacuation target nodes identified via distance-to-burned transform.

Coordinate order:
- Unprojected WGS84: (lon, lat) for geometries and Shapely coordinates.
- Continuous and discrete (row, col) coordinates for grid indexing.
"""

import math
from typing import Any, Dict, List, Optional, Tuple, Union
import networkx as nx
import numpy as np
import scipy.ndimage
from shapely.geometry import LineString, Point

from core.geo import haversine_m, lonlat_to_rc
from core.models import EvacParams, GridSpec, SpreadResult


def annotate_edges(
    G: nx.MultiDiGraph,
    spread: SpreadResult,
    grid: GridSpec,
    evac: EvacParams,
) -> nx.MultiDiGraph:
    """Annotate road graph edges with travel times and fire arrival times.

    For each directed edge:
    - tt_min: Travel time in minutes calculated as length / (speed * speed_factor).
    - fire_min: Earliest fire arrival time in minutes sampled along the edge geometry
      at intervals of <= grid.res_m.

    Args:
        G: NetworkX MultiDiGraph of drivable roads.
        spread: Fire spread simulation result containing arrival_min raster.
        grid: Grid specification for spatial transformations.
        evac: Evacuation routing parameters including speed_factor.

    Returns:
        nx.MultiDiGraph: The graph with 'tt_min' and 'fire_min' attributes on all edges.
    """
    arrival_grid = spread.arrival_min
    ny, nx_grid = grid.ny, grid.nx
    res_m = float(grid.res_m)
    speed_factor = max(0.01, float(evac.speed_factor))

    for u, v, key, data in G.edges(keys=True, data=True):
        # 1. Compute travel time in minutes
        length_m = float(data.get("length", 10.0))
        speed_kph = float(data.get("speed_kph", 30.0))
        effective_speed_m_per_min = (speed_kph * 1000.0 / 60.0) * speed_factor
        tt_min = length_m / max(effective_speed_m_per_min, 0.1)
        data["tt_min"] = tt_min

        # 2. Extract edge geometry in (lon, lat) coordinates
        geom: Optional[LineString] = data.get("geometry")
        if geom is None:
            u_node = G.nodes[u]
            v_node = G.nodes[v]
            geom = LineString([(float(u_node["x"]), float(u_node["y"])),
                               (float(v_node["x"]), float(v_node["y"]))])

        # 3. Sample along geometry at intervals <= res_m
        geom_length = geom.length  # degrees length
        # Approximate number of sample steps from length_m
        n_steps = max(1, int(math.ceil(length_m / res_m)))

        # Uniform distances along geometry in degrees
        distances = [i / n_steps * geom_length for i in range(n_steps + 1)]
        sample_pts = [geom.interpolate(d) for d in distances]
        sample_lons = np.array([pt.x for pt in sample_pts], dtype=float)
        sample_lats = np.array([pt.y for pt in sample_pts], dtype=float)

        # 4. Vectorised conversion from (lon, lat) to grid (row, col)
        r_cont, c_cont = lonlat_to_rc(grid, sample_lons, sample_lats)
        r_idx = np.round(r_cont).astype(int)
        c_idx = np.round(c_cont).astype(int)

        # Filter points within grid bounds
        valid_mask = (r_idx >= 0) & (r_idx < ny) & (c_idx >= 0) & (c_idx < nx_grid)

        if not np.any(valid_mask):
            fire_min = float("inf")
        else:
            valid_r = r_idx[valid_mask]
            valid_c = c_idx[valid_mask]
            sampled_arrivals = arrival_grid[valid_r, valid_c]
            fire_min = float(np.min(sampled_arrivals))

        data["fire_min"] = fire_min

    return G


def compute_safe_targets(
    G: nx.MultiDiGraph,
    spread: SpreadResult,
    grid: GridSpec,
    shelters: List[Tuple[str, float, float, str]],
    evac: EvacParams,
) -> Dict[int, Dict[str, Optional[str]]]:
    """Identify safe target destinations and designated shelter nodes.

    A node is deemed a safe target iff:
    1. It lies inside the simulation grid boundary.
    2. node_fire_min == inf (fire never reaches the node within the horizon).
    3. Distance from the node to the nearest burned/burning cell >= evac.safe_dist_m.
    If the burned mask is completely empty (no fire), all nodes in G are safe targets.

    Args:
        G: NetworkX MultiDiGraph of the road network.
        spread: Fire spread simulation result.
        grid: Simulation grid specification.
        shelters: List of shelter tuples (name, lat, lon, kind).
        evac: Evacuation parameters including safe_dist_m.

    Returns:
        Dict[int, Dict[str, Optional[str]]]: Mapping of target node ID to
        {"shelter": shelter_name | None}.
    """
    arrival_grid = spread.arrival_min
    ny, nx_grid = grid.ny, grid.nx
    res_m = float(grid.res_m)
    safe_dist_m = float(evac.safe_dist_m)

    burned = arrival_grid < float("inf")
    burned_any = bool(np.any(burned))

    if burned_any:
        # Distance transform in metres: distance from unburned cells to nearest burned cell
        dist_to_burn_m = scipy.ndimage.distance_transform_edt(~burned) * res_m
    else:
        dist_to_burn_m = None

    safe_targets: Dict[int, Dict[str, Optional[str]]] = {}

    for node_id, data in G.nodes(data=True):
        lon = float(data["x"])
        lat = float(data["y"])

        if not burned_any:
            # If no fire exists, all graph nodes are safe
            is_safe = True
        else:
            r_c, c_c = lonlat_to_rc(grid, lon, lat)
            r_idx = int(round(float(r_c)))
            c_idx = int(round(float(c_c)))

            if 0 <= r_idx < ny and 0 <= c_idx < nx_grid:
                node_fire_min = float(arrival_grid[r_idx, c_idx])
                node_dist_m = float(dist_to_burn_m[r_idx, c_idx])
                is_safe = math.isinf(node_fire_min) and (node_dist_m >= safe_dist_m)
            else:
                is_safe = False

        if is_safe:
            # Check if any designated shelter is within 300 m of this node
            matching_shelter_name: Optional[str] = None
            for sh_name, sh_lat, sh_lon, _ in shelters:
                if haversine_m(lon, lat, sh_lon, sh_lat) <= 300.0:
                    matching_shelter_name = sh_name
                    break

            safe_targets[node_id] = {"shelter": matching_shelter_name}

    return safe_targets

