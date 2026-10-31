"""Unit tests for OpenStreetMap road graph, settlements, and shelters."""

from unittest.mock import MagicMock, patch
import geopandas as gpd
import networkx as nx
import numpy as np
import osmnx as ox
import pytest
from shapely.geometry import Point

from core.data.osm import (
    DEFAULT_HWY_SPEEDS,
    FALLBACK_SPEED_KPH,
    _format_bbox_for_osmnx,
    get_road_graph,
    get_settlements,
    get_shelters,
)
from core.errors import FeedError
from core.models import AOI, Settlement


def test_osmnx_bbox_order() -> None:
    """Test OSMnx 2.x bbox format is strictly (left, bottom, right, top) = (west, south, east, north)."""
    aoi = AOI(west=-120.5, south=38.0, east=-120.1, north=38.4)
    bbox = _format_bbox_for_osmnx(aoi)

    assert bbox == (-120.5, 38.0, -120.1, 38.4)
    assert bbox[0] == aoi.west
    assert bbox[1] == aoi.south
    assert bbox[2] == aoi.east
    assert bbox[3] == aoi.north


def test_speed_default_mapping() -> None:
    """Test highway speed-default mapping and travel time computation on a procedural graph."""
    G = nx.MultiDiGraph()
    G.graph["crs"] = "EPSG:4326"

    # Add test nodes with required x, y spatial coordinates
    G.add_node(1, x=-120.0, y=38.0)
    G.add_node(2, x=-120.001, y=38.001)

    highway_types = [
        ("residential", 25.0),
        ("tertiary", 35.0),
        ("secondary", 45.0),
        ("primary", 55.0),
        ("trunk", 60.0),
        ("unclassified", 30.0),
        ("track", 15.0),
        ("service", 15.0),
        ("unknown_future_highway", FALLBACK_SPEED_KPH),
    ]

    for idx, (hwy, expected_speed) in enumerate(highway_types):
        G.add_edge(1, 2, key=idx, length=100.0, highway=hwy)

    G = ox.routing.add_edge_speeds(G, hwy_speeds=DEFAULT_HWY_SPEEDS, fallback=FALLBACK_SPEED_KPH)
    G = ox.routing.add_edge_travel_times(G)

    for idx, (hwy, expected_speed) in enumerate(highway_types):
        edge_data = G.edges[1, 2, idx]
        assert edge_data["speed_kph"] == expected_speed, f"Mismatch for highway={hwy}"

        # travel_time (seconds) = length (m) / (speed (km/h) * 1000 / 3600)
        expected_travel_time = 100.0 / (expected_speed * 1000.0 / 3600.0)
        assert pytest.approx(edge_data["travel_time"], rel=1e-3) == expected_travel_time


def test_settlement_deduplication_and_node_snapping() -> None:
    """Test node snapping, place rank prioritization, and 300 m deduplication on a procedural graph."""
    aoi = AOI(west=-120.2, south=37.9, east=-119.9, north=38.2)

    # Build procedural road graph with two separated nodes
    G = nx.MultiDiGraph()
    G.graph["crs"] = "EPSG:4326"
    G.add_node(100, x=-120.0, y=38.0)
    G.add_node(200, x=-120.1, y=38.1)
    G.add_edge(100, 200, key=0, length=15000.0, highway="primary")

    # Synthetic features to simulate Overpass features_from_bbox output
    # Big Town and Little Hamlet are ~60m apart and both snap to Node 100.
    # Distant Village is ~600m from Big Town and also snaps to Node 100.
    # Second Town snaps to Node 200.
    # Unnamed Place has empty name and must be dropped.
    data = [
        {
            "name": "Big Town",
            "place": "town",
            "osmid": 1001,
            "geometry": Point(-120.0004, 38.0004),
        },
        {
            "name": "Little Hamlet",
            "place": "hamlet",
            "osmid": 1002,
            "geometry": Point(-120.0008, 38.0008),
        },
        {
            "name": "Distant Village",
            "place": "village",
            "osmid": 1003,
            "geometry": Point(-120.0060, 38.0040),
        },
        {
            "name": "Second Town",
            "place": "town",
            "osmid": 1004,
            "geometry": Point(-120.1002, 38.1002),
        },
        {
            "name": None,  # Should be dropped
            "place": "village",
            "osmid": 1005,
            "geometry": Point(-120.1005, 38.1005),
        },
    ]
    gdf = gpd.GeoDataFrame(data, crs="EPSG:4326")

    with patch("osmnx.features_from_bbox", return_value=gdf):
        settlements = get_settlements(aoi, G)

    names = [s.name for s in settlements]
    assert "Big Town" in names
    assert "Little Hamlet" not in names, "Little Hamlet should be deduplicated (within 300m of Big Town on node 100)"
    assert "Distant Village" in names, "Distant Village should be kept (>300m away on node 100)"
    assert "Second Town" in names
    assert None not in names

    # Verify node snapping
    big_town = next(s for s in settlements if s.name == "Big Town")
    assert big_town.node == 100
    assert isinstance(big_town.node, int)

    second_town = next(s for s in settlements if s.name == "Second Town")
    assert second_town.node == 200


def test_simulate_api_failure_raises_feed_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that SIMULATE_API_FAILURE=overpass triggers FeedError at download step."""
    monkeypatch.setenv("SIMULATE_API_FAILURE", "overpass")
    aoi = AOI(west=-120.5, south=38.0, east=-120.1, north=38.4)
    G = nx.MultiDiGraph()

    with pytest.raises(FeedError) as exc_info:
        get_road_graph(aoi)
    assert "Simulated Overpass API failure" in str(exc_info.value)

    with pytest.raises(FeedError) as exc_info_settlements:
        get_settlements(aoi, G)
    assert "Simulated Overpass API failure" in str(exc_info_settlements.value)

    with pytest.raises(FeedError) as exc_info_shelters:
        get_shelters(aoi)
    assert "Simulated Overpass API failure" in str(exc_info_shelters.value)

