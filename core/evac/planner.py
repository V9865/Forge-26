"""Time-dependent evacuation route planner and settlement scheduler.

Implements:
1. Time-dependent Dijkstra algorithm evaluating dynamic edge fire arrival constraints.
2. Monotone binary search for the latest safe departure deadline.
3. Settlement risk classification (NOT_THREATENED, ALREADY_BURNING, EVACUATE, TRAPPED).

Mathematical justification:
Feasibility is monotone in departure time because all fire-avoidance constraints
are upper-bound deadlines:
    t_u + tt_min(e) + buffer_min <= fire_min(e)
Delaying departure (increasing t_0) shifts arrival times upwards at every downstream node:
    t_v(t_0') >= t_v(t_0) for all t_0' > t_0.
Therefore, if a route is infeasible at t_0, it is strictly infeasible for all t > t_0.
This monotonicity guarantees that earliest-arrival labels are optimal (Bellman's
principle of optimality holds) and binary search correctly determines the latest
feasible departure time.
"""

import heapq
import math
from typing import Any, Dict, List, Optional, Set, Tuple
import networkx as nx
import numpy as np
from shapely.geometry import LineString

from core.evac.graph_prep import compute_safe_targets
from core.geo import haversine_m, lonlat_to_rc
from core.models import EvacParams, GridSpec, Settlement, SettlementPlan, SpreadResult


def earliest_safe_route(
    G: nx.MultiDiGraph,
    source_node: int,
    depart_min: float,
    targets: Dict[int, Dict[str, Optional[str]]],
    evac: EvacParams,
    node_fire_arrivals: Optional[Dict[int, float]] = None,
) -> Optional[Tuple[List[int], float]]:
    """Compute the earliest-arrival fire-safe route from source_node to any safe target.

    Uses time-dependent Dijkstra search where the distance label represents the
    elapsed clock time (minutes from scenario start).
    Edge relaxation enforces the dynamic safety constraint:
        t_u + tt_min + evac.buffer_min <= fire_min

    Target selection prefers designated shelter targets if their arrival time is
    within 5.0 minutes of the earliest reachable non-shelter target.

    Args:
        G: Prepared MultiDiGraph with 'tt_min' and 'fire_min' attributes on edges.
        source_node: Graph node ID where evacuation originates.
        depart_min: Departure clock time in minutes.
        targets: Safe target dictionary mapping node_id -> {"shelter": name | None}.
        evac: Evacuation parameters including buffer_min.
        node_fire_arrivals: Optional precomputed fire arrival times at graph nodes.

    Returns:
        Optional[Tuple[List[int], float]]: (path_nodes, travel_duration_min) or None.
    """
    if source_node not in G:
        return None

    buffer_min = float(evac.buffer_min)

    # 1. Source feasibility check: cannot depart if source is burned or burns before buffer
    if node_fire_arrivals is not None:
        source_fire_min = node_fire_arrivals.get(source_node, float("inf"))
        if source_fire_min <= (depart_min + buffer_min):
            return None

    # Immediate match: if source is already a safe target
    if source_node in targets:
        return [source_node], 0.0

    # Priority queue stores tuples: (clock_time, current_node, path)
    # Using node counter to prevent comparisons between node objects on equal clock times
    counter = 0
    pq: List[Tuple[float, int, int, List[int]]] = [(depart_min, counter, source_node, [source_node])]

    # Earliest arrival time recorded for each node
    earliest_arrival: Dict[int, float] = {source_node: depart_min}

    best_non_shelter: Optional[Tuple[List[int], float]] = None
    cutoff_time = float("inf")

    while pq:
        clock_time, _, u, path = heapq.heappop(pq)

        if clock_time > earliest_arrival.get(u, float("inf")):
            continue

        # Check if clock_time exceeds the 5-minute shelter preference window
        if clock_time > cutoff_time:
            break

        # Check if u is a target node
        if u in targets:
            is_shelter = targets[u].get("shelter") is not None
            travel_min = clock_time - depart_min

            if is_shelter:
                # Prefer shelter target immediately if within cutoff
                return path, travel_min

            if best_non_shelter is None:
                best_non_shelter = (path, travel_min)
                # Allow search to continue up to 5 minutes to find a shelter target
                cutoff_time = clock_time + 5.0

        # Explore outgoing edges from u
        for v in G.successors(u):
            # Select the fastest feasible parallel edge from u to v
            best_edge_tt: Optional[float] = None

            for key, edge_data in G[u][v].items():
                tt_min = float(edge_data.get("tt_min", 1.0))
                fire_min = float(edge_data.get("fire_min", float("inf")))

                # Dynamic safety constraint: must clear edge before fire arrives + buffer
                if (clock_time + tt_min + buffer_min) <= fire_min:
                    if best_edge_tt is None or tt_min < best_edge_tt:
                        best_edge_tt = tt_min

            if best_edge_tt is not None:
                arrival_at_v = clock_time + best_edge_tt
                if arrival_at_v < earliest_arrival.get(v, float("inf")):
                    earliest_arrival[v] = arrival_at_v
                    counter += 1
                    heapq.heappush(pq, (arrival_at_v, counter, v, path + [v]))

    return best_non_shelter


def latest_departure(
    G: nx.MultiDiGraph,
    source_node: int,
    targets: Dict[int, Dict[str, Optional[str]]],
    evac: EvacParams,
    horizon_min: float = 720.0,
    node_fire_arrivals: Optional[Dict[int, float]] = None,
) -> Optional[float]:
    """Find the latest departure deadline for safe evacuation via monotone binary search.

    Monotonicity property:
    Because fire arrival times are non-decreasing deadlines along edges, delaying
    departure always delays arrival at every node. If an evacuation is impossible at
    time t, it is guaranteed impossible for any t' > t. Hence, binary search in
    [0, horizon_min] is guaranteed to converge to the latest safe departure time.

    Args:
        G: Prepared MultiDiGraph.
        source_node: Settlement origin node.
        targets: Safe target nodes mapping.
        evac: Evacuation routing parameters.
        horizon_min: Simulation time horizon in minutes (default 720).
        node_fire_arrivals: Optional node fire arrival times.

    Returns:
        Optional[float]: Latest departure time in minutes from scenario start, or None
                         if even immediate departure (t=0) is cut/impossible.
    """
    # 1. Base feasibility check at t = 0
    route_at_zero = earliest_safe_route(
        G, source_node, 0.0, targets, evac, node_fire_arrivals=node_fire_arrivals
    )
    if route_at_zero is None:
        return None

    # 2. Binary search for largest feasible depart_min with 1.0 minute tolerance
    low = 0.0
    high = float(horizon_min)

    # Check if feasible at horizon
    route_at_horizon = earliest_safe_route(
        G, source_node, high, targets, evac, node_fire_arrivals=node_fire_arrivals
    )
    if route_at_horizon is not None:
        return float(round(high, 1))

    while (high - low) > 1.0:
        mid = (low + high) / 2.0
        route = earliest_safe_route(
            G, source_node, mid, targets, evac, node_fire_arrivals=node_fire_arrivals
        )
        if route is not None:
            low = mid
        else:
            high = mid

    return float(round(low, 1))


def _extract_route_lonlat(G: nx.MultiDiGraph, path_nodes: List[int]) -> List[Tuple[float, float]]:
    """Convert sequence of graph nodes to continuous (lon, lat) route coordinates."""
    if not path_nodes:
        return []

    if len(path_nodes) == 1:
        n = path_nodes[0]
        return [(float(G.nodes[n]["x"]), float(G.nodes[n]["y"]))]

    coords: List[Tuple[float, float]] = []

    for i in range(len(path_nodes) - 1):
        u = path_nodes[i]
        v = path_nodes[i + 1]

        # Pick edge between u and v
        best_data: Optional[Dict[str, Any]] = None
        for key, data in G[u][v].items():
            if best_data is None or data.get("tt_min", 0) < best_data.get("tt_min", 0):
                best_data = data

        geom = best_data.get("geometry") if best_data else None

        if geom is not None and isinstance(geom, LineString):
            seg_coords = [(float(pt[0]), float(pt[1])) for pt in geom.coords]
            # Ensure geometry direction matches u -> v
            u_pt = (float(G.nodes[u]["x"]), float(G.nodes[u]["y"]))
            dist_start = (seg_coords[0][0] - u_pt[0]) ** 2 + (seg_coords[0][1] - u_pt[1]) ** 2
            dist_end = (seg_coords[-1][0] - u_pt[0]) ** 2 + (seg_coords[-1][1] - u_pt[1]) ** 2
            if dist_end < dist_start:
                seg_coords.reverse()
        else:
            seg_coords = [
                (float(G.nodes[u]["x"]), float(G.nodes[u]["y"])),
                (float(G.nodes[v]["x"]), float(G.nodes[v]["y"])),
            ]

        if not coords:
            coords.extend(seg_coords)
        else:
            coords.extend(seg_coords[1:])

    return coords


def plan_settlements(
    G: nx.MultiDiGraph,
    settlements: List[Settlement],
    spread: SpreadResult,
    grid: GridSpec,
    shelters: List[Tuple[str, float, float, str]],
    evac: EvacParams,
    horizon_min: float = 720.0,
) -> List[SettlementPlan]:
    """Generate evacuation plans and departure deadlines for all threatened settlements.

    For each settlement:
    1. fire_arrival_min: minimum arrival time within a 300 m radius of settlement point.
    2. Status classification:
       - NOT_THREATENED: if fire_arrival_min == inf.
       - ALREADY_BURNING: if fire_arrival_min <= 0.0.
       - EVACUATE: if safe route exists at depart_min = 0.0 (determines depart_by_min).
       - TRAPPED: if no safe route exists at t=0 (recommends shelter-in-place or airlift).

    Args:
        G: Prepared MultiDiGraph with 'tt_min' and 'fire_min' attributes.
        settlements: List of settlements to plan for.
        spread: Fire spread simulation result.
        grid: Simulation grid specification.
        shelters: List of shelter coordinates and kinds.
        evac: Evacuation parameters.
        horizon_min: Time horizon in minutes.

    Returns:
        List[SettlementPlan]: Comprehensive evacuation schedules and routes.
    """
    arrival_grid = spread.arrival_min
    ny, nx_grid = grid.ny, grid.nx
    res_m = float(grid.res_m)

    # Compute safe evacuation target nodes
    targets = compute_safe_targets(G, spread, grid, shelters, evac)

    # Precompute fire arrival times at graph nodes
    node_fire_arrivals: Dict[int, float] = {}
    for n, data in G.nodes(data=True):
        r_c, c_c = lonlat_to_rc(grid, float(data["x"]), float(data["y"]))
        r_idx = int(round(float(r_c)))
        c_idx = int(round(float(c_c)))
        if 0 <= r_idx < ny and 0 <= c_idx < nx_grid:
            node_fire_arrivals[n] = float(arrival_grid[r_idx, c_idx])
        else:
            node_fire_arrivals[n] = float("inf")

    # Cell radius for 300 m neighborhood check
    radius_cells = max(1, int(math.ceil(300.0 / res_m)))

    plans: List[SettlementPlan] = []

    for s in settlements:
        # Sample fire arrival within 300 m radius of settlement location
        r_c, c_c = lonlat_to_rc(grid, s.lon, s.lat)
        r_center = int(round(float(r_c)))
        c_center = int(round(float(c_c)))

        r_min_bound = max(0, r_center - radius_cells)
        r_max_bound = min(ny - 1, r_center + radius_cells)
        c_min_bound = max(0, c_center - radius_cells)
        c_max_bound = min(nx_grid - 1, c_center + radius_cells)

        local_arrivals: List[float] = []
        for r_cand in range(r_min_bound, r_max_bound + 1):
            for c_cand in range(c_min_bound, c_max_bound + 1):
                # Check spatial distance in metres
                cell_lon = grid.x0 + (c_cand + 0.5) * res_m
                cell_lat = grid.y0 - (r_cand + 0.5) * res_m
                # Approximate distance in metres from center
                dy = (r_cand - r_center) * res_m
                dx = (c_cand - c_center) * res_m
                if (dx * dx + dy * dy) <= (300.0 * 300.0):
                    local_arrivals.append(float(arrival_grid[r_cand, c_cand]))

        if local_arrivals:
            fire_arrival_min: Optional[float] = float(np.min(local_arrivals))
        else:
            fire_arrival_min = float("inf")

        # Classify status
        if math.isinf(fire_arrival_min):
            status = "NOT_THREATENED"
            plans.append(
                SettlementPlan(
                    settlement=s,
                    status=status,
                    fire_arrival_min=None,
                    depart_by_min=None,
                    route_lonlat=[],
                    route_travel_min=None,
                    naive_cut=None,
                    note="No fire threat predicted within simulation horizon.",
                )
            )
            continue

        if fire_arrival_min <= 0.0:
            status = "ALREADY_BURNING"
            plans.append(
                SettlementPlan(
                    settlement=s,
                    status=status,
                    fire_arrival_min=0.0,
                    depart_by_min=0.0,
                    route_lonlat=[],
                    route_travel_min=None,
                    naive_cut=True,
                    note="Fire is already present at settlement coordinates.",
                )
            )
            continue

        # For threatened settlement, verify route from snapped node
        snapped_node = s.node
        if snapped_node is None or snapped_node not in G:
            status = "TRAPPED"
            plans.append(
                SettlementPlan(
                    settlement=s,
                    status=status,
                    fire_arrival_min=fire_arrival_min,
                    depart_by_min=None,
                    route_lonlat=[],
                    route_travel_min=None,
                    naive_cut=True,
                    note="Settlement is disconnected from the road network. Immediate aerial rescue required.",
                )
            )
            continue

        # Solve earliest safe route at t=0
        route_res = earliest_safe_route(
            G, snapped_node, 0.0, targets, evac, node_fire_arrivals=node_fire_arrivals
        )

        if route_res is not None:
            path_nodes, travel_duration = route_res
            depart_by = latest_departure(
                G,
                snapped_node,
                targets,
                evac,
                horizon_min=horizon_min,
                node_fire_arrivals=node_fire_arrivals,
            )
            route_coords = _extract_route_lonlat(G, path_nodes)

            plans.append(
                SettlementPlan(
                    settlement=s,
                    status="EVACUATE",
                    fire_arrival_min=fire_arrival_min,
                    depart_by_min=depart_by,
                    route_lonlat=route_coords,
                    route_travel_min=travel_duration,
                    naive_cut=None,  # Evaluated by naive comparison
                    note=f"Safe evacuation route available to target node {path_nodes[-1]}.",
                )
            )
        else:
            plans.append(
                SettlementPlan(
                    settlement=s,
                    status="TRAPPED",
                    fire_arrival_min=fire_arrival_min,
                    depart_by_min=None,
                    route_lonlat=[],
                    route_travel_min=None,
                    naive_cut=True,
                    note="No feasible route escapes fire front. Recommend shelter-in-place or airlift.",
                )
            )

    return plans

