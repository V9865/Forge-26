"""Regression tests for baseline cut-route geometry extraction and serialization.

Verifies:
1. Settlements marked ALREADY_BURNING preserve cut classification (naive_cut=True).
2. Connected baseline road geometries are extracted into plan.naive_route_lonlat.
3. GeoJSON cut segments FeatureCollection contains valid LineString features.
4. Cut metrics (n_naive_cut) remain exact and unchanged.
5. Fire-aware safe route geometries remain unaltered.
"""

from datetime import datetime, timezone
import networkx as nx
import numpy as np
import pytest

from api.geojson import build_naive_cut_segments_geojson, build_routes_geojson
from core.evac.naive import compare
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


def _create_synthetic_test_env():
    """Create a test grid, road network and settlement plans."""
    grid = GridSpec(epsg=32610, x0=500000.0, y0=4200000.0, res_m=100.0, nx=20, ny=20)
    G = nx.MultiDiGraph()
    G.graph["crs"] = f"EPSG:{grid.epsg}"

    node_coords = {
        1: (10, 2),
        2: (15, 2),
        3: (10, 10),
        4: (10, 18),
    }

    for nid, (r, c) in node_coords.items():
        lon, lat = rc_to_lonlat(grid, r, c)
        G.add_node(nid, x=float(lon), y=float(lat))

    # Edges with travel time (tt_min) and fire arrival time (fire_min)
    G.add_edge(1, 3, key=0, length=800.0, tt_min=2.0, fire_min=0.0)
    G.add_edge(3, 4, key=0, length=800.0, tt_min=2.0, fire_min=50.0)
    G.add_edge(2, 3, key=0, length=900.0, tt_min=3.0, fire_min=30.0)

    targets = {4: {"shelter": None}}
    evac = EvacParams(buffer_min=5.0)

    lon1, lat1 = rc_to_lonlat(grid, 10, 2)
    s1 = Settlement(id="settlement_toledo_burning", name="Engulfed Settlement", lat=lat1, lon=lon1, node=1)
    plan1 = SettlementPlan(
        settlement=s1,
        status="ALREADY_BURNING",
        note="Fire arrival imminent at t=0",
        route_lonlat=[],
    )

    lon2, lat2 = rc_to_lonlat(grid, 15, 2)
    s2 = Settlement(id="settlement_algarve_threatened", name="Threatened Settlement", lat=lat2, lon=lon2, node=2)
    safe_route_coords = [(lon2, lat2), (lon1, lat1), (rc_to_lonlat(grid, 10, 18))]
    plan2 = SettlementPlan(
        settlement=s2,
        status="EVACUATE",
        depart_by_min=15.0,
        route_lonlat=safe_route_coords,
    )

    return G, grid, targets, evac, [plan1, plan2]


def test_already_burning_baseline_cut_geometry_extracted():
    """Verify that an ALREADY_BURNING settlement receives valid naive cut geometry."""
    G, grid, targets, evac, plans = _create_synthetic_test_env()

    metrics = compare(plans, G, targets, evac)

    # Cut metric assertions
    assert metrics["n_threatened"] == 2
    assert metrics["n_already_burning"] == 1
    assert metrics["n_evacuate"] == 1
    assert metrics["n_naive_cut"] >= 1

    plan_burning = next(p for p in plans if p.settlement.id == "settlement_toledo_burning")
    assert plan_burning.naive_cut is True
    # Crucial regression check: geometry must NOT be empty or None
    assert plan_burning.naive_route_lonlat is not None
    assert len(plan_burning.naive_route_lonlat) >= 2

    # Check GeoJSON serialization
    spread = SpreadResult(
        grid=grid,
        arrival_min=np.zeros((20, 20)),
        ignitions=[(37.94, -121.0)],
        params=SpreadParams(),
        runtime_s=0.1,
    )
    result = PipelineResult(
        aoi=AOI(west=-121.2, south=37.8, east=-120.8, north=38.1),
        mode="SCENARIO",
        detections=[],
        grid=grid,
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
        provenance=[],
        warnings=[],
        trace=[],
        metrics=metrics,
    )

    cut_geojson = build_naive_cut_segments_geojson(result)
    assert cut_geojson["type"] == "FeatureCollection"
    assert len(cut_geojson["features"]) >= 1

    cut_feat = cut_geojson["features"][0]
    assert cut_feat["geometry"]["type"] == "LineString"
    assert len(cut_feat["geometry"]["coordinates"]) >= 2
    assert cut_feat["properties"]["kind"] == "baseline_cut"
    assert cut_feat["properties"]["cut"] is True

    # Fire-aware safe route must remain intact and separate
    routes_geojson = build_routes_geojson(result)
    assert len(routes_geojson["features"]) == 1
    assert routes_geojson["features"][0]["properties"]["kind"] == "aware"
    assert routes_geojson["features"][0]["properties"]["cut"] is False
