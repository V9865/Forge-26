"""Unit and integration tests for EmberRoute FastAPI layer.

Tests:
- Submit and poll asynchronous workflow
- 60-second identical input job caching
- Input validation (AOI extents, ignition containment, resolution)
- Error mapping across pipeline exception codes
- Monitor enable / disable toggling
- GZip compression on large responses
- Root fallback JSON when frontend/dist is absent
- Health, clusters, and validation endpoints
"""

from datetime import datetime, timezone
import time
from typing import Any, List, Optional
import numpy as np
import pytest
from starlette.testclient import TestClient

from api.main import _RATE_LIMIT_STORE, app, job_manager
from api.schemas import PlanRequest
from core.errors import FeedError
from core.models import (
    AOI,
    GridSpec,
    PipelineResult,
    Settlement,
    SettlementPlan,
    SpreadParams,
    SpreadResult,
    WindSeries,
)
from core.pipeline import PipelineError


def _make_dummy_pipeline_result() -> PipelineResult:
    """Build a procedural PipelineResult for fast API testing."""
    aoi = AOI(west=7.45, south=46.20, east=7.65, north=46.35)
    wind = WindSeries(
        start_utc=datetime.now(timezone.utc),
        speed_ms=[5.0] * 24,
        dir_from_deg=[240.0] * 24,
        rh=[40.0] * 24,
        temp_c=[20.0] * 24,
        source="Open-Meteo",
        fetched_at_utc=datetime.now(timezone.utc),
        is_override=False,
        is_stale=False,
    )
    grid = GridSpec(epsg=32632, x0=380000.0, y0=5120000.0, res_m=90, nx=10, ny=10)
    spread = SpreadResult(
        grid=grid,
        arrival_min=np.full((10, 10), np.inf),
        ignitions=[(46.28, 7.55)],
        params=SpreadParams(),
        runtime_s=0.2,
    )
    s = Settlement(id="v_1", name="Village_Alpha", lat=46.25, lon=7.50, node=100)
    plan = SettlementPlan(
        settlement=s,
        status="EVACUATE",
        fire_arrival_min=120.0,
        depart_by_min=60.0,
        route_lonlat=[(7.50, 46.25), (7.52, 46.27)],
        route_travel_min=15.0,
        naive_cut=False,
        note="Clear route",
    )
    return PipelineResult(
        aoi=aoi,
        mode="SCENARIO",
        detections=[],
        wind=wind,
        spread=spread,
        plans=[plan],
        metrics={"n_threatened": 1, "n_evacuate": 1, "n_trapped": 0, "n_settlements_total": 1},
        provenance=[],
        warnings=["Test warning"],
        trace=[{"step": "init", "status": "ok", "duration_ms": 1.0}],
    )


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """Test client with pipeline runner monkeypatched to fast procedural stub."""
    _RATE_LIMIT_STORE.clear()
    monkeypatch.setattr(
        "api.jobs.run_pipeline",
        lambda *args, **kwargs: _make_dummy_pipeline_result(),
    )
    monkeypatch.setattr(
        "core.agent.llm.is_available",
        lambda *args, **kwargs: False,
    )
    return TestClient(app)


def test_root_fallback(client: TestClient) -> None:
    """Verify GET / returns JSON status fallback when frontend/dist is not built."""
    resp = client.get("/")
    assert resp.status_code == 200
    data = resp.json()
    assert "EmberRoute" in data.get("name", "")


def test_health_endpoint(client: TestClient) -> None:
    """Verify GET /api/health returns feed health and LLM diagnostics."""
    resp = client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert "feeds" in data
    assert "llm" in data["feeds"]


def test_clusters_endpoint(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify GET /api/clusters returns list of cluster items."""
    monkeypatch.setattr(
        "api.main.find_active_clusters",
        lambda hours, top_n: [
            {
                "center_lat": 46.28,
                "center_lon": 7.55,
                "count": 12,
                "total_frp": 85.0,
                "suggested_aoi": {"west": 7.45, "south": 46.20, "east": 7.65, "north": 46.35},
            }
        ],
    )
    resp = client.get("/api/clusters")
    assert resp.status_code == 200
    clusters = resp.json()
    assert len(clusters) == 1
    assert clusters[0]["count"] == 12


def test_submit_and_poll_flow(client: TestClient) -> None:
    """Verify POST /api/plan returns 202 and GET /api/jobs/{id} polls to done."""
    body = {
        "aoi": {"west": 7.45, "south": 46.20, "east": 7.65, "north": 46.35},
        "mode": "SCENARIO",
        "ignition": {"lat": 46.28, "lon": 7.55},
        "resolution_m": 90,
    }
    resp = client.post("/api/plan", json=body)
    assert resp.status_code == 202
    data = resp.json()
    assert "job_id" in data
    job_id = data["job_id"]

    # Poll until done (fast stub finishes almost immediately)
    poll_data = {}
    for _ in range(50):
        poll_resp = client.get(f"/api/jobs/{job_id}")
        assert poll_resp.status_code == 200
        poll_data = poll_resp.json()
        if poll_data["status"] in ("done", "error"):
            break
        time.sleep(0.1)

    assert poll_data["status"] == "done"
    assert poll_data["progress"] == 1.0
    assert poll_data["result"] is not None
    assert poll_data["result"]["mode"] == "SCENARIO"
    assert "settlements" in poll_data["result"]
    assert "routes" in poll_data["result"]


def test_identical_input_caching(client: TestClient) -> None:
    """Verify identical requests within 60 seconds return the same job_id."""
    body = {
        "aoi": {"west": 7.45, "south": 46.20, "east": 7.65, "north": 46.35},
        "mode": "SCENARIO",
        "ignition": {"lat": 46.28, "lon": 7.55},
        "resolution_m": 90,
    }
    resp1 = client.post("/api/plan", json=body)
    assert resp1.status_code == 202
    jid1 = resp1.json()["job_id"]

    resp2 = client.post("/api/plan", json=body)
    assert resp2.status_code == 202
    jid2 = resp2.json()["job_id"]

    assert jid1 == jid2, "Identical request within 60s must reuse the existing job"


def test_input_validation(client: TestClient) -> None:
    """Verify input validation rules on POST /api/plan."""
    # 1. AOI width > 0.6 degrees
    bad_aoi = {
        "aoi": {"west": 7.00, "south": 46.20, "east": 7.70, "north": 46.35},  # 0.70 deg wide
        "mode": "SCENARIO",
    }
    r1 = client.post("/api/plan", json=bad_aoi)
    assert r1.status_code == 422
    assert "0.6 degrees" in r1.json()["error"]["message"]

    # 2. Inverted coordinates (east <= west)
    inv_aoi = {
        "aoi": {"west": 7.65, "south": 46.20, "east": 7.45, "north": 46.35},
        "mode": "SCENARIO",
    }
    r2 = client.post("/api/plan", json=inv_aoi)
    assert r2.status_code == 422

    # 3. Ignition outside AOI
    out_ign = {
        "aoi": {"west": 7.45, "south": 46.20, "east": 7.65, "north": 46.35},
        "mode": "SCENARIO",
        "ignition": {"lat": 40.00, "lon": 7.50},  # Latitude 40 is outside [46.20, 46.35]
    }
    r3 = client.post("/api/plan", json=out_ign)
    assert r3.status_code == 422
    assert "inside the AOI" in r3.json()["error"]["message"]

    # 4. Invalid resolution
    bad_res = {
        "aoi": {"west": 7.45, "south": 46.20, "east": 7.65, "north": 46.35},
        "mode": "SCENARIO",
        "resolution_m": 45,  # Must be 60, 90, or 120
    }
    r4 = client.post("/api/plan", json=bad_res)
    assert r4.status_code == 422


def test_error_mapping(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify that pipeline exceptions are mapped to the correct job error detail."""
    def raise_feed_down(*args: Any, **kwargs: Any):
        raise PipelineError("FEED_DOWN", "Simulated external feed outage")

    monkeypatch.setattr("api.jobs.run_pipeline", raise_feed_down)

    body = {
        "aoi": {"west": 7.45, "south": 46.20, "east": 7.65, "north": 46.35},
        "mode": "LIVE",
    }
    resp = client.post("/api/plan", json=body)
    assert resp.status_code == 202
    job_id = resp.json()["job_id"]

    for _ in range(20):
        poll_resp = client.get(f"/api/jobs/{job_id}")
        poll_data = poll_resp.json()
        if poll_data["status"] in ("done", "error"):
            break
        time.sleep(0.1)

    assert poll_data["status"] == "error"
    assert poll_data["error"]["code"] == "FEED_DOWN"


def test_monitor_endpoints(client: TestClient) -> None:
    """Verify POST /api/monitor and GET /api/monitor enable and disable."""
    # 1. Enable monitor
    enable_body = {
        "enabled": True,
        "aoi": {"west": 7.45, "south": 46.20, "east": 7.65, "north": 46.35},
        "mode": "SCENARIO",
        "poll_s": 30,
    }
    r1 = client.post("/api/monitor", json=enable_body)
    assert r1.status_code == 200
    assert r1.json()["enabled"] is True

    # 2. Check status
    r2 = client.get("/api/monitor")
    assert r2.status_code == 200
    assert r2.json()["enabled"] is True

    # 3. Disable monitor
    disable_body = {"enabled": False}
    r3 = client.post("/api/monitor", json=disable_body)
    assert r3.status_code == 200
    assert r3.json()["enabled"] is False


def test_validation_endpoint(client: TestClient) -> None:
    """Verify GET /api/validation returns parsed historical event table."""
    resp = client.get("/api/validation")
    assert resp.status_code == 200
    data = resp.json()
    assert data["available"] is True
    assert len(data["events"]) >= 1


def test_gzip_compression(client: TestClient) -> None:
    """Verify GZipMiddleware compresses large responses when requested."""
    resp = client.get("/openapi.json", headers={"Accept-Encoding": "gzip"})
    assert resp.status_code == 200
    # Responses > 1024 bytes will include content-encoding: gzip
    assert resp.headers.get("content-encoding") == "gzip"

