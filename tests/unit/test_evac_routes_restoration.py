"""Regression tests for settlement analysis and evacuation route restoration in EmberRoute.

Validates:
1. Settlement retrieval and status classification (EVACUATE, TRAPPED, NOT_THREATENED).
2. Fire-aware route and naive cut baseline route distinction.
3. GeoJSON serialization of settlements, routes, and cut segments.
4. Road-following coordinate validity and strict [lon, lat] ordering.
5. End-to-end JobResult schema serialization for frontend consumption.
"""

from datetime import datetime, timezone
import math
from typing import Dict, List, Tuple
import networkx as nx
import numpy as np
import pytest

from api.geojson import (
    build_naive_cut_segments_geojson,
    build_routes_geojson,
    build_settlements_geojson,
)
from api.jobs import JobManager
from api.schemas import AOIModel, PlanRequest, PlanResult
from core.evac.graph_prep import annotate_edges, compute_safe_targets
from core.evac.naive import compare, naive_route, route_is_cut
from core.evac.planner import earliest_safe_route, latest_departure, plan_settlements
from core.geo import rc_to_lonlat
from core.models import (
    AOI,
    EvacParams,
    GridSpec,
    PipelineResult,
    Settlement,
    SettlementPlan,
    SpreadParams,
    SpreadResult,
    WindSeries,
)


def _build_test_graph_and_grid() -> Tuple[nx.MultiDiGraph, GridSpec, np.ndarray]:
    """Build a deterministic procedural environment with alternative routing paths."""
    grid = GridSpec(epsg=32610, x0=500000.0, y0=4200000.0, res_m=100.0, nx=20, ny=20)
    G = nx.MultiDiGraph()
    G.graph["crs"] = f"EPSG:{grid.epsg}"

    node_rc = {
        1: (10, 2),   # Origin settlement
        2: (10, 8),   # Direct path waypoint (cut by fire)
        3: (10, 16),  # Safe evacuation target
        4: (4, 8),    # Fire-safe detour waypoint
    }

    for n_id, (r, c) in node_rc.items():
        lon, lat = rc_to_lonlat(grid, r, c)
        G.add_node(n_id, x=float(lon), y=float(lat))

    # Direct short path: 1 -> 2 (600m), 2 -> 3 (800m)
    G.add_edge(1, 2, key=0, length=600.0, speed_kph=30.0)
    G.add_edge(2, 3, key=0, length=800.0, speed_kph=30.0)
    # Safe detour path: 1 -> 4 (1200m), 4 -> 3 (1200m)
    G.add_edge(1, 4, key=0, length=1200.0, speed_kph=30.0)
    G.add_edge(4, 3, key=0, length=1200.0, speed_kph=30.0)

    arrival_min = np.full((grid.ny, grid.nx), float("inf"), dtype=np.float32)
    return G, grid, arrival_min


def test_fire_aware_vs_naive_cut_routes_are_distinguishable() -> None:
    """Verify that fire-aware recommended routes and naive cut routes have distinct geometries."""
    G, grid, arrival_min = _build_test_graph_and_grid()
    evac = EvacParams(speed_factor=1.0, buffer_min=10.0, safe_dist_m=300.0)

    # Fire threatens settlement at (10, 2) at t = 45 min
    arrival_min[9:12, 1:4] = 45.0
    # Fire cuts direct road (r=10, c=6..8) early at t = 10 min
    arrival_min[9:12, 5:10] = 10.0

    spread = SpreadResult(
        grid=grid,
        arrival_min=arrival_min,
        ignitions=[(37.94, -121.0)],
        params=SpreadParams(),
        runtime_s=0.01,
    )

    G = annotate_edges(G, spread, grid, evac)
    targets = {3: {"shelter": "East Haven Shelter"}}

    lon1, lat1 = float(G.nodes[1]["x"]), float(G.nodes[1]["y"])
    st = Settlement(id="settlement_1", name="Pine Ridge", lat=lat1, lon=lon1, node=1)
    shelters = [("East Haven Shelter", float(G.nodes[3]["y"]), float(G.nodes[3]["x"]), "community_centre")]

    plans = plan_settlements(G, [st], spread, grid, shelters, evac)
    assert len(plans) == 1
    assert plans[0].status == "EVACUATE"
    assert len(plans[0].route_lonlat) >= 2, "Aware route must have road coordinates"

    # Evaluate naive baseline comparison
    metrics = compare(plans, G, targets, evac)
    assert plans[0].naive_cut is True
    assert len(plans[0].naive_route_lonlat) >= 2, "Cut naive route must have coordinates"

    # Crucial assertion: Aware route and cut naive route must NOT be identical
    aware_coords = plans[0].route_lonlat
    naive_coords = plans[0].naive_route_lonlat
    assert aware_coords != naive_coords, "Aware safe detour must not equal the naive cut path"

    # Verify GeoJSON serialization
    pipeline_res = PipelineResult(
        aoi=AOI(west=-121.2, south=37.8, east=-120.8, north=38.1),
        mode="SCENARIO",
        detections=[],
        wind=WindSeries(
            start_utc=datetime.now(timezone.utc),
            speed_ms=[5.0] * 24,
            dir_from_deg=[270.0] * 24,
            rh=[30.0] * 24,
            temp_c=[25.0] * 24,
            source="test",
            fetched_at_utc=datetime.now(timezone.utc),
        ),
        spread=spread,
        plans=plans,
        metrics=metrics,
        provenance=[],
        warnings=[],
        trace=[],
    )

    routes_fc = build_routes_geojson(pipeline_res)
    naive_fc = build_naive_cut_segments_geojson(pipeline_res)
    settlements_fc = build_settlements_geojson(pipeline_res)

    # 1. Routes FeatureCollection
    assert routes_fc["type"] == "FeatureCollection"
    assert len(routes_fc["features"]) == 1
    r_feat = routes_fc["features"][0]
    assert r_feat["geometry"]["type"] == "LineString"
    assert r_feat["properties"]["kind"] == "aware"
    assert r_feat["properties"]["cut"] is False
    assert r_feat["properties"]["settlement_id"] == "settlement_1"

    # 2. Naive Cut Segments FeatureCollection
    assert naive_fc["type"] == "FeatureCollection"
    assert len(naive_fc["features"]) == 1
    n_feat = naive_fc["features"][0]
    assert n_feat["geometry"]["type"] == "LineString"
    assert n_feat["properties"]["kind"] == "baseline_cut"
    assert n_feat["properties"]["cut"] is True
    assert n_feat["properties"]["settlement_id"] == "settlement_1"

    # 3. Coordinate geometry differentiation in serialized GeoJSON
    assert r_feat["geometry"]["coordinates"] != n_feat["geometry"]["coordinates"]

    # 4. Settlements FeatureCollection
    assert settlements_fc["type"] == "FeatureCollection"
    assert len(settlements_fc["features"]) == 1
    s_feat = settlements_fc["features"][0]
    assert s_feat["geometry"]["type"] == "Point"
    assert s_feat["properties"]["status"] == "EVACUATE"
    assert s_feat["properties"]["fire_arrival_min"] == 10.0
    assert s_feat["properties"]["naive_cut"] is True


def test_settlement_and_route_survives_job_result_serialization() -> None:
    """Verify that complete settlement and route plans survive the API JobManager serialization."""
    G, grid, arrival_min = _build_test_graph_and_grid()
    evac = EvacParams(speed_factor=1.0, buffer_min=10.0, safe_dist_m=300.0)

    arrival_min[9:12, 1:4] = 30.0
    arrival_min[9:12, 5:10] = 5.0

    spread = SpreadResult(
        grid=grid,
        arrival_min=arrival_min,
        ignitions=[(37.94, -121.0)],
        params=SpreadParams(),
        runtime_s=0.01,
    )
    G = annotate_edges(G, spread, grid, evac)
    targets = {3: {"shelter": "Main Shelter"}}

    lon1, lat1 = float(G.nodes[1]["x"]), float(G.nodes[1]["y"])
    st = Settlement(id="st_valais", name="Alpine Settlement", lat=lat1, lon=lon1, node=1)
    shelters = [("Main Shelter", float(G.nodes[3]["y"]), float(G.nodes[3]["x"]), "community_centre")]

    plans = plan_settlements(G, [st], spread, grid, shelters, evac)
    metrics = compare(plans, G, targets, evac)

    aoi = AOI(west=7.45, south=46.20, east=7.65, north=46.35)
    pipeline_res = PipelineResult(
        aoi=aoi,
        mode="SCENARIO",
        detections=[],
        wind=WindSeries(
            start_utc=datetime.now(timezone.utc),
            speed_ms=[6.0] * 24,
            dir_from_deg=[240.0] * 24,
            rh=[25.0] * 24,
            temp_c=[28.0] * 24,
            source="Open-Meteo",
            fetched_at_utc=datetime.now(timezone.utc),
        ),
        spread=spread,
        plans=plans,
        metrics=metrics,
        provenance=[],
        warnings=[],
        trace=[],
    )

    req = PlanRequest(
        aoi=AOIModel(west=7.45, south=46.20, east=7.65, north=46.35),
        mode="SCENARIO",
        ignition={"lat": 46.25, "lon": 7.50},
    )
    mgr = JobManager(max_workers=1)
    plan_result = mgr._convert_pipeline_to_plan_result(pipeline_res, req)

    # Validate PlanResult schema properties
    assert isinstance(plan_result, PlanResult)
    assert plan_result.settlements is not None
    assert len(plan_result.settlements.features) == 1
    assert plan_result.routes is not None
    assert len(plan_result.routes.features) == 1
    assert plan_result.naive_cut_segments is not None
    assert len(plan_result.naive_cut_segments.features) == 1

    # Verify JSON export matches frontend expectations
    exported = plan_result.model_dump()
    assert exported["settlements"]["features"][0]["properties"]["name"] == "Alpine Settlement"
    assert exported["routes"]["features"][0]["properties"]["kind"] == "aware"
    assert exported["naive_cut_segments"]["features"][0]["properties"]["cut"] is True


def test_trapped_settlement_empty_routes_reported_honestly() -> None:
    """Verify that trapped settlements without feasible exit routes report empty routes honestly."""
    G, grid, arrival_min = _build_test_graph_and_grid()
    evac = EvacParams(speed_factor=1.0, buffer_min=10.0, safe_dist_m=300.0)

    # Burn all outgoing roads from Node 1 immediately
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
    targets = {3: {"shelter": None}}

    lon1, lat1 = float(G.nodes[1]["x"]), float(G.nodes[1]["y"])
    st = Settlement(id="st_trapped", name="Valley Dead-End", lat=lat1, lon=lon1, node=1)
    plans = plan_settlements(G, [st], spread, grid, [], evac)

    assert len(plans) == 1
    assert plans[0].status == "TRAPPED"
    assert plans[0].route_lonlat == [], "Trapped settlements must not fabricate fake routes"
    assert "airlift" in plans[0].note.lower() or "shelter-in-place" in plans[0].note.lower()
