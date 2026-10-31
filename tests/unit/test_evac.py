"""Unit tests for time-dependent evacuation routing, scheduling, and comparison."""

import math
from typing import Dict, List, Tuple
import networkx as nx
import numpy as np
import pytest

from core.evac.graph_prep import annotate_edges, compute_safe_targets
from core.evac.naive import compare, naive_route, route_is_cut
from core.evac.planner import earliest_safe_route, latest_departure, plan_settlements
from core.geo import rc_to_lonlat
from core.models import EvacParams, GridSpec, Settlement, SpreadParams, SpreadResult


def _create_synthetic_environment() -> Tuple[nx.MultiDiGraph, GridSpec, np.ndarray]:
    """Build a deterministic procedural environment for testing evacuation algorithms."""
    # 20x20 grid at 100m resolution in UTM 10N
    grid = GridSpec(epsg=32610, x0=500000.0, y0=4200000.0, res_m=100.0, nx=20, ny=20)

    # MultiDiGraph with 4 nodes:
    # Node 1: Origin settlement at (r=10, c=2)
    # Node 2: Waypoint along short path at (r=10, c=8)
    # Node 3: Target destination at (r=10, c=16)
    # Node 4: Waypoint along longer detour path at (r=4, c=8)
    G = nx.MultiDiGraph()
    G.graph["crs"] = f"EPSG:{grid.epsg}"

    node_rc = {
        1: (10, 2),
        2: (10, 8),
        3: (10, 16),
        4: (4, 8),
    }

    for n_id, (r, c) in node_rc.items():
        lon, lat = rc_to_lonlat(grid, r, c)
        G.add_node(n_id, x=float(lon), y=float(lat))

    # Edges:
    # Short path: 1 -> 2 (600m), 2 -> 3 (800m)
    # Long path: 1 -> 4 (1200m), 4 -> 3 (1200m)
    G.add_edge(1, 2, key=0, length=600.0, speed_kph=30.0)
    G.add_edge(2, 3, key=0, length=800.0, speed_kph=30.0)
    G.add_edge(1, 4, key=0, length=1200.0, speed_kph=30.0)
    G.add_edge(4, 3, key=0, length=1200.0, speed_kph=30.0)

    # Initialize arrival raster
    arrival_min = np.full((grid.ny, grid.nx), float("inf"), dtype=np.float32)

    return G, grid, arrival_min


def test_fire_cuts_short_road_and_rescued_by_replan() -> None:
    """Test: Fire cuts the short road at a known time; a longer detour survives.

    Planner chooses the long road; naive picks the short road and route_is_cut is True.
    """
    G, grid, arrival_min = _create_synthetic_environment()
    evac = EvacParams(speed_factor=1.0, buffer_min=10.0, safe_dist_m=300.0)

    # Fire threatens Pine Village (Node 1 at r=10, c=2) at t = 45 min
    arrival_min[9:12, 1:4] = 45.0

    # Fire cuts across the short road (r=10, c=6..8) early at t = 10.0 min
    arrival_min[9:12, 5:10] = 10.0

    # The detour route through row 4 remains unburned (fire = inf)
    spread = SpreadResult(
        grid=grid,
        arrival_min=arrival_min,
        ignitions=[(37.94, -121.0)],
        params=SpreadParams(),
        runtime_s=0.01,
    )

    G = annotate_edges(G, spread, grid, evac)
    targets = {3: {"shelter": "Community Shelter"}}

    # Short edge (1 -> 2) has fire_min = 10.0.
    # At t_depart = 0: travel time is 600m / (30 km/h * 1000/60) = 1.2 min.
    # Feasibility check: 0 + 1.2 + 10.0 buffer = 11.2 > 10.0 fire_min (CUT!)
    assert G[1][2][0]["fire_min"] <= 10.0

    # 1. Naive fire-blind route picks the short path
    naive_path = naive_route(G, source_node=1, targets=targets)
    assert naive_path == [1, 2, 3]
    assert route_is_cut(G, naive_path, depart_min=0.0, evac=evac) is True

    # 2. Fire-aware planner avoids cut short path and selects long detour [1, 4, 3]
    safe_res = earliest_safe_route(G, source_node=1, depart_min=0.0, targets=targets, evac=evac)
    assert safe_res is not None
    path, travel_min = safe_res
    assert path == [1, 4, 3]
    assert travel_min > 0.0

    # 3. Compare metrics show 1 settlement rescued by replan
    lon1, lat1 = float(G.nodes[1]["x"]), float(G.nodes[1]["y"])
    st = Settlement(id="1", name="Pine Village", lat=lat1, lon=lon1, node=1)
    shelters = [("Community Shelter", float(G.nodes[3]["y"]), float(G.nodes[3]["x"]), "community_centre")]

    plans = plan_settlements(G, [st], spread, grid, shelters, evac)
    assert len(plans) == 1
    assert plans[0].status == "EVACUATE"

    metrics = compare(plans, G, targets, evac)
    assert metrics["n_threatened"] == 1
    assert metrics["n_evacuate"] == 1
    assert metrics["n_naive_cut"] == 1
    assert metrics["n_rescued_by_replan"] == 1
    assert plans[0].naive_cut is True


def test_departure_deadline_monotone_boundary() -> None:
    """Test: Leaving at latest_departure succeeds, departing one minute later fails."""
    G, grid, arrival_min = _create_synthetic_environment()
    evac = EvacParams(speed_factor=1.0, buffer_min=10.0, safe_dist_m=300.0)

    # Cut short road completely so only detour path [1, 4, 3] can be taken
    arrival_min[9:12, 5:10] = 5.0

    # Detour road passes through (r=4, c=8). Fire reaches here at t = 50.0 min.
    arrival_min[3:6, 7:10] = 50.0

    spread = SpreadResult(
        grid=grid,
        arrival_min=arrival_min,
        ignitions=[(37.94, -121.0)],
        params=SpreadParams(),
        runtime_s=0.01,
    )
    G = annotate_edges(G, spread, grid, evac)
    targets = {3: {"shelter": None}}

    latest_dep = latest_departure(G, source_node=1, targets=targets, evac=evac, horizon_min=100.0)
    assert latest_dep is not None
    assert 34.0 <= latest_dep <= 36.5

    # Leaving at latest_dep must succeed
    route_on_time = earliest_safe_route(G, 1, depart_min=latest_dep, targets=targets, evac=evac)
    assert route_on_time is not None

    # Leaving 1.5 minutes after deadline must fail
    route_late = earliest_safe_route(G, 1, depart_min=latest_dep + 1.5, targets=targets, evac=evac)
    assert route_late is None


def test_settlement_enclosed_by_fire_is_trapped() -> None:
    """Test: Settlement enclosed by fire on all roads is classified as TRAPPED."""
    G, grid, arrival_min = _create_synthetic_environment()
    evac = EvacParams(speed_factor=1.0, buffer_min=10.0, safe_dist_m=300.0)

    # All outgoing roads from Node 1 burned immediately at t = 2.0 min
    arrival_min[9:12, 1:4] = 2.0
    arrival_min[3:6, 1:4] = 2.0

    spread = SpreadResult(
        grid=grid,
        arrival_min=arrival_min,
        ignitions=[(37.94, -121.0)],
        params=SpreadParams(),
        runtime_s=0.01,
    )
    G = annotate_edges(G, spread, grid, evac)

    lon1, lat1 = float(G.nodes[1]["x"]), float(G.nodes[1]["y"])
    st = Settlement(id="1", name="Trapped Hamlet", lat=lat1, lon=lon1, node=1)
    shelters = [("Safe Shelter", float(G.nodes[3]["y"]), float(G.nodes[3]["x"]), "hospital")]

    plans = plan_settlements(G, [st], spread, grid, shelters, evac)
    assert len(plans) == 1
    assert plans[0].status == "TRAPPED"
    assert "shelter-in-place" in plans[0].note.lower() or "airlift" in plans[0].note.lower()
    assert plans[0].depart_by_min is None


def test_settlement_far_from_fire_is_not_threatened() -> None:
    """Test: Settlement located far from fire arrival is classified as NOT_THREATENED."""
    G, grid, arrival_min = _create_synthetic_environment()
    evac = EvacParams(speed_factor=1.0, buffer_min=10.0, safe_dist_m=300.0)

    # Fire is only active at the far corner (r=0, c=0)
    arrival_min[0:2, 0:2] = 20.0

    spread = SpreadResult(
        grid=grid,
        arrival_min=arrival_min,
        ignitions=[(37.94, -121.0)],
        params=SpreadParams(),
        runtime_s=0.01,
    )
    G = annotate_edges(G, spread, grid, evac)

    # Settlement at Node 1 (r=10, c=2) is miles away from (0, 0)
    lon1, lat1 = float(G.nodes[1]["x"]), float(G.nodes[1]["y"])
    st = Settlement(id="1", name="Safe Haven", lat=lat1, lon=lon1, node=1)
    shelters = [("Safe Shelter", float(G.nodes[3]["y"]), float(G.nodes[3]["x"]), "hospital")]

    plans = plan_settlements(G, [st], spread, grid, shelters, evac)
    assert len(plans) == 1
    assert plans[0].status == "NOT_THREATENED"
    assert plans[0].depart_by_min is None
    assert plans[0].route_travel_min is None


def test_buffer_min_reduces_departure_deadline() -> None:
    """Test: Increasing buffer_min reduces latest_departure deadline by approximately the delta."""
    G, grid, arrival_min = _create_synthetic_environment()

    # Cut short road
    arrival_min[9:12, 5:10] = 5.0
    # Fire reaches detour road at t = 60.0 min
    arrival_min[3:6, 7:10] = 60.0

    spread = SpreadResult(
        grid=grid,
        arrival_min=arrival_min,
        ignitions=[(37.94, -121.0)],
        params=SpreadParams(),
        runtime_s=0.01,
    )

    targets = {3: {"shelter": None}}

    evac10 = EvacParams(speed_factor=1.0, buffer_min=10.0, safe_dist_m=300.0)
    G10 = annotate_edges(G.copy(), spread, grid, evac10)
    dep10 = latest_departure(G10, 1, targets, evac10, horizon_min=100.0)

    evac20 = EvacParams(speed_factor=1.0, buffer_min=20.0, safe_dist_m=300.0)
    G20 = annotate_edges(G.copy(), spread, grid, evac20)
    dep20 = latest_departure(G20, 1, targets, evac20, horizon_min=100.0)

    assert dep10 is not None
    assert dep20 is not None

    # Increasing buffer by 10 minutes should reduce latest departure by ~10 minutes
    delta = dep10 - dep20
    assert pytest.approx(delta, abs=1.5) == 10.0
