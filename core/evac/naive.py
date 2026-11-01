"""Fire-blind naive evacuation baseline and plan comparison module.

Provides:
1. Fire-blind shortest path routing (naive baseline).
2. Cut detection identifying if a naive evacuation route would be intercepted by fire.
3. Comparative benchmarking quantifying how many lives/settlements are rescued by
   fire-aware replanning.
"""

from typing import Any, Dict, List, Optional
import networkx as nx
import numpy as np

from core.models import EvacParams, SettlementPlan


def naive_route(
    G: nx.MultiDiGraph,
    source_node: int,
    targets: Dict[int, Any],
) -> Optional[List[int]]:
    """Compute the fire-blind shortest route from source_node to any safe target.

    Uses standard Dijkstra shortest path purely minimizing edge travel time (tt_min),
    completely ignoring fire rate-of-spread and arrival times.

    Args:
        G: Prepared MultiDiGraph with 'tt_min' edge weights.
        source_node: Settlement origin node.
        targets: Set or dict of target node IDs.

    Returns:
        Optional[List[int]]: Sequence of node IDs in the naive route, or None if no
                             path exists to any target.
    """
    if source_node not in G or not targets:
        return None

    if source_node in targets:
        return [source_node]

    try:
        lengths, paths = nx.single_source_dijkstra(G, source_node, weight="tt_min")
    except Exception:
        return None

    valid_targets = [t for t in targets if t in lengths]
    if not valid_targets:
        return None

    best_target = min(valid_targets, key=lambda t: lengths[t])
    return paths[best_target]


def route_is_cut(
    G: nx.MultiDiGraph,
    path: List[int],
    depart_min: float = 0.0,
    evac: Optional[EvacParams] = None,
) -> bool:
    """Evaluate whether an evacuation route is intercepted by fire.

    Simulates travellers departing at depart_min and moving along the path.
    An edge is cut if:
        t_current + tt_min + buffer_min > fire_min

    Args:
        G: MultiDiGraph with 'tt_min' and 'fire_min' attributes.
        path: Ordered list of graph node IDs.
        depart_min: Departure clock time in minutes.
        evac: Evacuation parameters including buffer_min.

    Returns:
        bool: True if any edge along the route is intercepted by fire; False otherwise.
    """
    if not path or len(path) < 2:
        return False

    buffer_min = float(evac.buffer_min) if evac is not None else 10.0
    clock_time = float(depart_min)

    for i in range(len(path) - 1):
        u = path[i]
        v = path[i + 1]

        if not G.has_edge(u, v):
            return True

        # Parallel edge: take the fastest one
        best_data = min(G[u][v].values(), key=lambda d: float(d.get("tt_min", float("inf"))))
        tt_min = float(best_data.get("tt_min", 1.0))
        fire_min = float(best_data.get("fire_min", float("inf")))

        # Check safety deadline
        if (clock_time + tt_min + buffer_min) > fire_min:
            return True

        clock_time += tt_min

    return False


def compare(
    plans: List[SettlementPlan],
    G: nx.MultiDiGraph,
    targets: Dict[int, Any],
    evac: EvacParams,
) -> Dict[str, Any]:
    """Compare fire-aware evacuation plans against the naive fire-blind baseline.

    Updates each SettlementPlan in place with naive_cut (True/False) and computes
    comparative metrics demonstrating the value of dynamic replanning.

    Args:
        plans: List of SettlementPlans produced by planner.py.
        G: Prepared road graph.
        targets: Safe destination nodes.
        evac: Evacuation parameters.

    Returns:
        Dict[str, Any]: Metrics summarizing threatened settlements, naive failures,
                        and lives rescued by fire-aware routing.
    """
    for plan in plans:
        # Settlements already burning or trapped without road connections
        if plan.status == "ALREADY_BURNING":
            plan.naive_cut = True
            continue

        if plan.status == "NOT_THREATENED":
            plan.naive_cut = False
            continue

        snapped_node = plan.settlement.node
        if snapped_node is None or snapped_node not in G:
            plan.naive_cut = True
            continue

        # Evaluate naive route
        naive_path = naive_route(G, snapped_node, targets)
        if naive_path is None:
            plan.naive_cut = True
        else:
            plan.naive_cut = route_is_cut(G, naive_path, depart_min=0.0, evac=evac)
            if plan.naive_cut:
                from core.evac.planner import _extract_route_lonlat
                plan.naive_route_lonlat = _extract_route_lonlat(G, naive_path)

    # Compute aggregate metrics
    threatened_statuses = {"EVACUATE", "TRAPPED", "ALREADY_BURNING"}
    threatened_plans = [p for p in plans if p.status in threatened_statuses]

    n_threatened = len(threatened_plans)
    n_evacuate = sum(1 for p in plans if p.status == "EVACUATE")
    n_trapped = sum(1 for p in plans if p.status == "TRAPPED")
    n_already_burning = sum(1 for p in plans if p.status == "ALREADY_BURNING")

    # Threatened settlements whose naive route is cut by fire
    n_naive_cut = sum(1 for p in threatened_plans if p.naive_cut)

    # Naive route is cut by fire, BUT fire-aware planner finds a viable alternative
    n_rescued_by_replan = sum(1 for p in plans if p.status == "EVACUATE" and p.naive_cut)

    # Departure time statistics
    depart_times = [
        float(p.depart_by_min)
        for p in plans
        if p.status == "EVACUATE" and p.depart_by_min is not None
    ]

    median_depart = float(np.median(depart_times)) if depart_times else None
    min_depart = float(np.min(depart_times)) if depart_times else None

    return {
        "n_threatened": n_threatened,
        "n_evacuate": n_evacuate,
        "n_trapped": n_trapped,
        "n_already_burning": n_already_burning,
        "n_naive_cut": n_naive_cut,
        "n_rescued_by_replan": n_rescued_by_replan,
        "median_depart_by_min": median_depart,
        "min_depart_by_min": min_depart,
    }

