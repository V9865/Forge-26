"""Integration tests for OpenStreetMap real data downloads."""

import pytest

from core.data.osm import get_road_graph, get_settlements, get_shelters
from core.models import AOI


@pytest.mark.integration
def test_real_osm_download_and_enrichment() -> None:
    """Download a real small bbox graph and assert nodes, travel_time edges, and settlements."""
    aoi = AOI(west=7.45, south=46.20, east=7.65, north=46.35)

    G = get_road_graph(aoi)
    assert len(G.nodes) > 0, "Road graph should have nodes"
    assert len(G.edges) > 0, "Road graph should have edges"

    # Assert edges have travel_time and speed_kph
    sample_edge = next(iter(G.edges(data=True)))
    u, v, data = sample_edge
    assert "speed_kph" in data, "Edge missing speed_kph"
    assert "travel_time" in data, "Edge missing travel_time"
    assert data["speed_kph"] > 0
    assert data["travel_time"] > 0

    # Assert settlements extraction
    settlements = get_settlements(aoi, G)
    assert len(settlements) >= 1, "Should find at least one settlement in AOI"
    for s in settlements:
        assert s.name, "Settlement must have a name"
        assert s.node in G.nodes, f"Settlement node {s.node} must exist in road graph"

    # Assert shelters extraction
    shelters = get_shelters(aoi)
    assert isinstance(shelters, list)
