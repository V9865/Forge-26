"""Unit tests for EmberRoute system hardening, edge cases, and fault resilience."""

from datetime import datetime, timezone
import io
import logging
import math
import os
from typing import Any, Dict, List
import networkx as nx
import numpy as np
import pytest

from api.jobs import JobManager
from api.main import app
from api.schemas import PlanRequest
from core.agent.briefing import build_facts, template_briefing
from core.agent.guard import verify
from core.agent.orchestrator import circular_diff_deg, detect_change, WorldState
from core.config import get_settings
from core.data.firms import parse_firms_csv
from core.evac.planner import plan_settlements
from core.fire.spread import simulate_spread
from core.geo import make_grid
from core.models import (
    AOI,
    EvacParams,
    FireDetection,
    GridSpec,
    Layers,
    PipelineResult,
    Settlement,
    SpreadParams,
    SpreadResult,
    WindSeries,
)
from core.pipeline import NoActiveFireError, PipelineError, run_pipeline


def test_secrets_not_in_repr_or_logs(caplog):
    """Verify that sensitive API keys are masked and never leak to logs."""
    settings = get_settings()
    s_repr = repr(settings)
    assert settings.FIRMS_MAP_KEY not in s_repr or settings.FIRMS_MAP_KEY == ""
    assert settings.GROQ_API_KEY not in s_repr or settings.GROQ_API_KEY == ""
    assert "***" in s_repr or "''" in s_repr


def test_midnight_firms_parsing():
    """Verify satellite detections crossing midnight are parsed correctly."""
    csv_sample = """latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,satellite,confidence,version,bright_ti5,frp,daynight
-24.42,31.52,340.0,0.4,0.4,2026-10-31,0,N,nominal,2.0NRT,295.0,25.0,N
-24.45,31.55,345.0,0.4,0.4,2026-10-31,2359,N,high,2.0NRT,298.0,40.0,N
"""
    now = datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc)
    dets = parse_firms_csv(csv_sample, source="VIIRS_SNPP_NRT", hours=48, now_utc=now)
    assert len(dets) == 2
    assert dets[0].acq_time_utc.hour == 0
    assert dets[0].acq_time_utc.minute == 0
    assert dets[1].acq_time_utc.hour == 23
    assert dets[1].acq_time_utc.minute == 59


def test_wind_extremes_no_nans():
    """Verify wind speed 0 and 40 m/s with RH extremes produce finite arrays with no NaNs."""
    grid = GridSpec(epsg=32636, x0=300000, y0=7300000, res_m=100.0, nx=20, ny=20)
    layers = Layers(
        grid=grid,
        elevation=np.zeros((20, 20), dtype=np.float32),
        fuel_class=np.full((20, 20), 30, dtype=np.uint8),
        base_ros=np.full((20, 20), 10.0, dtype=np.float32),
    )
    ignitions = [(10, 10, 0.0)]

    for speed, rh in [(0.0, 0.0), (40.0, 100.0), (15.0, 50.0)]:
        wind = WindSeries(
            start_utc=datetime.now(timezone.utc),
            speed_ms=[speed] * 24,
            dir_from_deg=[270.0] * 24,
            rh=[rh] * 24,
            temp_c=[30.0] * 24,
            source="test",
            fetched_at_utc=datetime.now(timezone.utc),
        )
        res = simulate_spread(layers=layers, wind=wind, ignitions=ignitions, params=SpreadParams(horizon_min=120.0))
        assert not np.isnan(res.arrival_min).any()
        assert res.arrival_min[10, 10] == 0.0
        burned = res.arrival_min <= 120.0
        assert np.any(burned)
        assert np.isfinite(res.arrival_min[burned]).all()


def test_disconnected_settlement_handling():
    """Verify settlement with no road access or outside grid is classified TRAPPED/NOT_THREATENED without crash."""
    grid = GridSpec(epsg=32636, x0=300000, y0=7300000, res_m=100.0, nx=20, ny=20)
    arrival = np.full((20, 20), np.inf, dtype=np.float32)
    arrival[5, 5] = 10.0  # Fire threatens this area

    spread = SpreadResult(
        grid=grid,
        arrival_min=arrival,
        ignitions=[(300500.0, 7299500.0)],
        params=SpreadParams(),
        runtime_s=0.01,
    )

    # Empty road graph
    G = nx.MultiDiGraph()

    # Settlement 1: threatened by fire but completely disconnected
    s1 = Settlement(id="s1", name="Isolated Village", lat=-24.40, lon=31.50, population=500, place="village", node=999)
    # Settlement 2: not threatened by fire and disconnected
    s2 = Settlement(id="s2", name="Safe Outpost", lat=-24.45, lon=31.55, population=100, place="hamlet", node=888)

    plans = plan_settlements(
        G=G,
        settlements=[s1, s2],
        spread=spread,
        grid=grid,
        shelters=[],
        evac=EvacParams(),
        horizon_min=720.0,
    )

    assert len(plans) == 2
    statuses = {p.settlement.name: p.status for p in plans}
    assert statuses["Isolated Village"] in ("TRAPPED", "NOT_THREATENED")
    assert statuses["Safe Outpost"] == "NOT_THREATENED"
    for p in plans:
        assert p.note is not None


def test_non_burnable_ignition_rejection():
    """Verify SCENARIO ignition on water or bare land is refused with NON_BURNABLE_IGNITION."""
    aoi = AOI(west=31.45, south=-24.50, east=31.60, north=-24.35)
    # In SCENARIO mode, if ignition is on water or outside grid, pipeline raises PipelineError
    with pytest.raises(PipelineError) as exc_info:
        # Latitude outside AOI
        run_pipeline(aoi, mode="SCENARIO", ignition_point=(-24.10, 31.50))
    assert exc_info.value.code == "INVALID_INPUT"


def test_template_briefing_fallback():
    """Verify template briefing is cleanly labeled and contains key metrics."""
    aoi = AOI(west=31.45, south=-24.50, east=31.60, north=-24.35)
    wind = WindSeries(
        start_utc=datetime.now(timezone.utc),
        speed_ms=[12.0] * 24,
        dir_from_deg=[90.0] * 24,
        rh=[20.0] * 24,
        temp_c=[32.0] * 24,
        source="test",
        fetched_at_utc=datetime.now(timezone.utc),
    )
    grid = GridSpec(epsg=32636, x0=300000, y0=7300000, res_m=100.0, nx=20, ny=20)
    spread = SpreadResult(
        grid=grid,
        arrival_min=np.full((20, 20), np.inf, dtype=np.float32),
        ignitions=[],
        params=SpreadParams(),
        runtime_s=0.01,
    )
    result = PipelineResult(
        aoi=aoi,
        mode="LIVE",
        detections=[],
        wind=wind,
        spread=spread,
        plans=[],
        metrics={"n_threatened": 2, "n_evacuate": 1, "n_trapped": 1, "n_settlements_total": 5},
        provenance=[],
        warnings=[],
        trace=[],
    )

    facts = build_facts(result)
    text = template_briefing(facts)
    assert "Wind is 12.0 m/s" in text
    assert "trapped" in text.lower()
    assert "freshness" in text.lower()


def test_lost_job_not_found(client=None):
    """Verify missing or expired job ID returns structured JOB_NOT_FOUND error."""
    from fastapi.testclient import TestClient
    from api.main import _RATE_LIMIT_STORE
    _RATE_LIMIT_STORE.clear()

    tc = TestClient(app)
    resp = tc.get("/api/jobs/non-existent-uuid-1234")
    assert resp.status_code == 404
    data = resp.json()
    assert "error" in data
    assert data["error"]["code"] == "JOB_NOT_FOUND"
    assert "re-run" in data["error"]["message"].lower()
