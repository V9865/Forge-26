"""Unit tests for EmberRoute LLM client, agent tools, and orchestrator.

Covers:
- Fake LLM tool calling loop success
- Invalid / repeated tool call -> deterministic fallback
- HTTP 429 adaptive retry (retry-after <= 5s waits once; > 5s moves to next provider)
- Daily token budget enforcement (raises LLMUnavailable without making API calls)
- Total provider exhaustion -> template fallback briefing
- State change detection (including circular wind direction wrap-around 350 -> 20 deg)
- LIVE mode with NO_FIRE never invents an ignition
- Tool summary compactness constraints (<= 300 tokens)
"""

from datetime import datetime, timezone
import json
from typing import Any, Dict, List, Optional
import pytest

from core.agent.llm import (
    LLMResponse,
    LLMUnavailable,
    chat,
    get_total_tokens_used,
    reset_total_tokens_used,
)
from core.agent.orchestrator import (
    CycleResult,
    Orchestrator,
    WorldState,
    circular_diff_deg,
    detect_change,
    diff,
)
from core.agent.tools import compact, estimate_tokens
from core.config import Settings, get_settings
from core.models import AOI, GridSpec, PipelineResult, Settlement, SettlementPlan, SpreadParams, SpreadResult, WindSeries
import numpy as np


# ---------------------------------------------------------------------------
# Procedural Mock Objects for Unit Tests
# ---------------------------------------------------------------------------

def _make_dummy_pipeline_result(
    n_settlements: int = 4,
    n_trapped: int = 1,
    n_evacuate: int = 2,
    warnings: Optional[List[str]] = None,
) -> PipelineResult:
    """Build a lightweight PipelineResult procedurally for unit tests."""
    aoi = AOI(west=7.45, south=46.20, east=7.65, north=46.35)
    wind = WindSeries(
        start_utc=datetime.now(timezone.utc),
        speed_ms=[6.5],
        dir_from_deg=[240.0],
        rh=[45.0],
        temp_c=[22.0],
        source="Open-Meteo",
        fetched_at_utc=datetime.now(timezone.utc),
        is_override=False,
        is_stale=False,
    )
    plans: List[SettlementPlan] = []
    for i in range(n_settlements):
        s_name = f"Village_{i+1}"
        s_obj = Settlement(id=f"v_{i+1}", name=s_name, lat=46.25 + i * 0.01, lon=7.50 + i * 0.01, node=100 + i)
        if i < n_trapped:
            status = "TRAPPED"
            arr = 45.0
            dep = None
            rt = []
            tt = None
        elif i < n_trapped + n_evacuate:
            status = "EVACUATE"
            arr = 120.0
            dep = 60.0
            rt = [(7.50, 46.25), (7.52, 46.27)]
            tt = 15.0
        else:
            status = "NOT_THREATENED"
            arr = float("inf")
            dep = None
            rt = []
            tt = None

        plans.append(
            SettlementPlan(
                settlement=s_obj,
                status=status,
                fire_arrival_min=arr,
                depart_by_min=dep,
                route_lonlat=rt,
                route_travel_min=tt,
                naive_cut=False,
                note=f"Plan note {i}",
            )
        )

    grid = GridSpec(epsg=32632, x0=380000.0, y0=5120000.0, res_m=90, nx=10, ny=10)
    spread = SpreadResult(
        grid=grid,
        arrival_min=np.full((10, 10), np.inf),
        ignitions=[(46.28, 7.55)],
        params=SpreadParams(),
        runtime_s=0.5,
    )

    return PipelineResult(
        aoi=aoi,
        mode="SCENARIO",
        detections=[],
        wind=wind,
        spread=spread,
        plans=plans,
        metrics={
            "n_settlements_total": n_settlements,
            "n_threatened": n_trapped + n_evacuate,
            "n_evacuate": n_evacuate,
            "n_trapped": n_trapped,
            "n_already_burning": 0,
            "n_not_threatened": n_settlements - (n_trapped + n_evacuate),
        },
        provenance=[],
        warnings=warnings or [],
        trace=[],
    )


# ---------------------------------------------------------------------------
# Unit Test Cases
# ---------------------------------------------------------------------------

def test_detect_change_and_circular_wind_shift() -> None:
    """Test detect_change conditions, specifically circular angular differences."""
    aoi = AOI(west=7.45, south=46.20, east=7.65, north=46.35)

    # 1. Circular difference math
    assert circular_diff_deg(350.0, 20.0) == 30.0
    assert circular_diff_deg(20.0, 350.0) == 30.0
    assert circular_diff_deg(350.0, 25.0) == 35.0
    assert circular_diff_deg(10.0, 50.0) == 40.0
    assert circular_diff_deg(180.0, 180.0) == 0.0

    state1 = WorldState(
        aoi=aoi,
        last_detection_hash="hash_a",
        last_wind_summary={"speed_ms": 10.0, "dir_from_deg": 350.0},
    )

    # 2. Wind shift <= 30 deg should NOT trigger
    state_no_shift = WorldState(
        aoi=aoi,
        last_detection_hash="hash_a",
        last_wind_summary={"speed_ms": 10.0, "dir_from_deg": 20.0},  # Exactly 30 deg
    )
    assert "WIND_DIR_SHIFT" not in detect_change(state1, state_no_shift)

    # 3. Wind shift > 30 deg DOES trigger
    state_shift = WorldState(
        aoi=aoi,
        last_detection_hash="hash_a",
        last_wind_summary={"speed_ms": 10.0, "dir_from_deg": 25.0},  # 35 deg shift
    )
    assert "WIND_DIR_SHIFT" in detect_change(state1, state_shift)

    # 4. Wind speed change (> 25% relative)
    state_spd = WorldState(
        aoi=aoi,
        last_detection_hash="hash_a",
        last_wind_summary={"speed_ms": 13.0, "dir_from_deg": 350.0},  # 30% increase
    )
    assert "WIND_SPEED_CHANGE" in detect_change(state1, state_spd)

    # 5. New detection hash
    state_det = WorldState(
        aoi=aoi,
        last_detection_hash="hash_b",
        last_wind_summary={"speed_ms": 10.0, "dir_from_deg": 350.0},
    )
    assert "NEW_DETECTIONS" in detect_change(state1, state_det)

    # 6. Feed recovery
    state_deg = WorldState(aoi=aoi, degraded={"firms": True})
    state_rec = WorldState(aoi=aoi, degraded={"firms": False})
    assert "FEED_RECOVERED" in detect_change(state_deg, state_rec)


def test_tool_summaries_size_cap() -> None:
    """Verify compact() helper truncates lists > 5 and caps token estimates at ~300."""
    large_payload = {
        "items": [{"id": i, "name": f"Settlement_{i}", "metrics": [1.23456, 7.89012]} for i in range(20)],
        "geometry": [[1.0, 2.0] for _ in range(500)],  # Should be pruned
        "arrival_grid": [[0.5] * 50 for _ in range(50)],  # Should be pruned
        "nested": {"sub": [float(x) for x in range(30)]},
    }

    compacted = compact(large_payload, max_tokens=300)
    json_str = json.dumps(compacted)
    tok_count = estimate_tokens(json_str)

    assert "geometry" not in compacted
    assert "arrival_grid" not in compacted
    assert len(compacted["items"]) <= 6  # 5 items + 1 omitted notice
    assert tok_count <= 300, f"Compacted token estimate {tok_count} exceeded 300"


def test_no_fire_never_creates_ignition(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify that in LIVE mode with zero detections, planner stops and never invents an ignition."""
    # Mock get_fire_detections to return zero detections
    monkeypatch.setattr(
        "core.agent.orchestrator.get_fire_detections",
        lambda aoi: {"status": "ok", "summary": {"count": 0, "detections": []}},
    )

    aoi = AOI(west=7.45, south=46.20, east=7.65, north=46.35)
    orch = Orchestrator(aoi=aoi, mode="LIVE")

    result = orch.run_deterministic_plan(aoi=aoi, mode="LIVE")
    assert result is None, "In LIVE mode with zero detections, result should be None (never invent an ignition)"


def test_fake_llm_tool_loop_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify LLM tool-calling loop executes tools in sequence and generates briefing."""
    dummy_res = _make_dummy_pipeline_result(n_settlements=3, n_trapped=1, n_evacuate=1)

    # Monkeypatch pipeline runner so tools return immediately
    monkeypatch.setattr(
        "core.agent.tools.run_pipeline",
        lambda *args, **kwargs: dummy_res,
    )
    monkeypatch.setattr(
        "core.agent.tools.fetch_detections",
        lambda *args, **kwargs: ([], type("Prov", (), {"source": "NASA FIRMS", "is_stale": False})()),
    )
    monkeypatch.setattr(
        "core.agent.tools.fetch_wind_series",
        lambda *args, **kwargs: (dummy_res.wind, type("Prov", (), {"source": "Open-Meteo", "is_stale": False})()),
    )

    call_index = 0

    def mock_chat(*args: Any, **kwargs: Any) -> LLMResponse:
        nonlocal call_index
        call_index += 1
        role = kwargs.get("role", "planner")

        if role == "planner":
            if call_index == 1:
                return LLMResponse(
                    text="Getting fire detections",
                    tool_calls=[{"id": "c1", "type": "function", "function": {"name": "get_fire_detections", "arguments": '{"aoi": {"west": 7.45, "south": 46.2, "east": 7.65, "north": 46.35}}'}}],
                    usage={"total_tokens": 50},
                    provider="mock_groq",
                    model="mock_model",
                )
            elif call_index == 2:
                return LLMResponse(
                    text="Getting weather",
                    tool_calls=[{"id": "c2", "type": "function", "function": {"name": "get_weather", "arguments": '{"center": {"lat": 46.28, "lon": 7.55}}'}}],
                    usage={"total_tokens": 50},
                    provider="mock_groq",
                    model="mock_model",
                )
            elif call_index == 3:
                return LLMResponse(
                    text="Running full plan",
                    tool_calls=[{"id": "c3", "type": "function", "function": {"name": "run_full_plan", "arguments": '{"aoi": {"west": 7.45, "south": 46.2, "east": 7.65, "north": 46.35}, "mode": "SCENARIO"}'}}],
                    usage={"total_tokens": 50},
                    provider="mock_groq",
                    model="mock_model",
                )
            else:
                return LLMResponse(
                    text="DONE",
                    tool_calls=[],
                    usage={"total_tokens": 10},
                    provider="mock_groq",
                    model="mock_model",
                )
        else:
            # Briefing role
            return LLMResponse(
                text="Wind is blowing at 6.5 m/s [F2]. Village_1 is TRAPPED with arrival at 45.0 min [F3].",
                tool_calls=[],
                usage={"total_tokens": 80},
                provider="mock_groq",
                model="mock_model",
            )

    monkeypatch.setattr("core.agent.orchestrator.chat", mock_chat)

    orch = Orchestrator(mode="SCENARIO")
    cycle = orch.run_cycle(reason="TEST_LOOP")

    assert cycle.result is not None
    assert len(cycle.trace) >= 4
    assert cycle.provider == "mock_groq"


def test_invalid_or_repeated_tool_call_deterministic_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify that repeated tool calls trigger immediate fallback to deterministic planner."""
    dummy_res = _make_dummy_pipeline_result(n_settlements=2)
    monkeypatch.setattr("core.agent.tools.run_pipeline", lambda *args, **kwargs: dummy_res)

    # Mock chat returns identical tool call twice in a row
    def mock_chat(*args: Any, **kwargs: Any) -> LLMResponse:
        return LLMResponse(
            text="Looping",
            tool_calls=[{"id": "c1", "type": "function", "function": {"name": "get_weather", "arguments": '{"center": {"lat": 46.28, "lon": 7.55}}'}}],
            usage={"total_tokens": 20},
            provider="mock_groq",
            model="mock_model",
        )

    monkeypatch.setattr("core.agent.orchestrator.chat", mock_chat)

    orch = Orchestrator(mode="SCENARIO")
    cycle = orch.run_cycle(reason="TEST_FALLBACK")

    assert cycle.result is not None
    # Trace must reflect fallback
    has_fallback = any("fallback" in t.get("step", "").lower() for t in cycle.trace)
    assert has_fallback, "Deterministic fallback should be logged in trace"


def test_token_budget_exceeded_no_api_call(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify that exceeding LLM_DAILY_TOKEN_BUDGET raises LLMUnavailable without making API calls."""
    reset_total_tokens_used()
    settings = Settings(LLM_DAILY_TOKEN_BUDGET=100)

    # Manually consume tokens up to budget
    from core.agent import llm
    llm._TOTAL_TOKENS_USED = 100

    api_called = False

    def mock_builder(*args: Any, **kwargs: Any):
        nonlocal api_called
        api_called = True
        raise AssertionError("API client should never be invoked when budget is exceeded")

    monkeypatch.setattr("core.agent.llm._build_client_for_spec", mock_builder)

    with pytest.raises(LLMUnavailable) as exc_info:
        chat(messages=[{"role": "user", "content": "hi"}], settings=settings)

    assert exc_info.value.reason == "budget"
    assert not api_called, "No external API call should be made when budget is exceeded"
    reset_total_tokens_used()


def test_every_provider_fails_template_briefing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify that when all LLM providers fail, template briefing is used and used_llm=False."""
    dummy_res = _make_dummy_pipeline_result(n_settlements=3, n_trapped=1, n_evacuate=1)
    monkeypatch.setattr("core.agent.tools.run_pipeline", lambda *args, **kwargs: dummy_res)

    def failing_chat(*args: Any, **kwargs: Any):
        raise LLMUnavailable("All providers failed", reason="exhausted")

    monkeypatch.setattr("core.agent.orchestrator.chat", failing_chat)

    orch = Orchestrator(mode="SCENARIO")
    cycle = orch.run_cycle(reason="TEST_EXHAUSTION")

    assert cycle.result is not None
    assert cycle.used_llm is False
    assert "TRAPPED" in cycle.briefing
    assert len(cycle.briefing) > 20


def test_http_429_adaptive_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify HTTP 429 adaptive backoff: waits <= 5s once, skips > 5s immediately."""
    import openai
    import httpx

    # Create dummy RateLimitErrors with custom Retry-After headers
    req = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")

    resp_short = httpx.Response(status_code=429, request=req, headers={"retry-after": "2"})
    err_short = openai.RateLimitError("Rate limit", response=resp_short, body=None)

    resp_long = httpx.Response(status_code=429, request=req, headers={"retry-after": "30"})
    err_long = openai.RateLimitError("Rate limit", response=resp_long, body=None)

    slept_durations: List[float] = []
    monkeypatch.setattr("time.sleep", lambda s: slept_durations.append(s))

    # Case 1: Short retry-after (2s) -> sleeps once and succeeds on retry
    attempts_short = 0

    class MockCompletionsShort:
        def create(self, *args: Any, **kwargs: Any) -> Any:
            nonlocal attempts_short
            attempts_short += 1
            if attempts_short == 1:
                raise err_short
            mock_choice = type("Choice", (), {"message": type("Msg", (), {"content": "ok", "tool_calls": None})()})()
            return type("Resp", (), {"choices": [mock_choice], "usage": type("Usage", (), {"prompt_tokens": 5, "completion_tokens": 5, "total_tokens": 10})()})()

    mock_client_short = type("Client", (), {"chat": type("Chat", (), {"completions": MockCompletionsShort()})()})()
    monkeypatch.setattr("core.agent.llm._build_client_for_spec", lambda spec, settings: (mock_client_short, "model"))

    settings = Settings(LLM_CHAIN="groq:m1", LLM_PLANNER_MODEL="groq:m1", GROQ_API_KEY="test")
    res1 = chat([{"role": "user", "content": "hi"}], settings=settings)
    assert res1.text == "ok"
    assert slept_durations == [2.0], f"Expected sleep 2.0s once, got {slept_durations}"

    # Case 2: Long retry-after (30s) -> moves immediately to next provider without sleeping 30s
    slept_durations.clear()
    providers_called: List[str] = []

    class MockCompletionsLong:
        def __init__(self, name: str) -> None:
            self.name = name

        def create(self, *args: Any, **kwargs: Any) -> Any:
            providers_called.append(self.name)
            if self.name == "m1":
                raise err_long
            mock_choice = type("Choice", (), {"message": type("Msg", (), {"content": "recovered", "tool_calls": None})()})()
            return type("Resp", (), {"choices": [mock_choice], "usage": type("Usage", (), {"prompt_tokens": 5, "completion_tokens": 5, "total_tokens": 10})()})()

    def mock_builder_long(spec: Any, s: Any) -> Any:
        return type("Client", (), {"chat": type("Chat", (), {"completions": MockCompletionsLong(spec.model)})()})(), spec.model

    monkeypatch.setattr("core.agent.llm._build_client_for_spec", mock_builder_long)
    settings_multi = Settings(LLM_CHAIN="groq:m1,groq:m2", LLM_PLANNER_MODEL="groq:m1", GROQ_API_KEY="test")
    res2 = chat([{"role": "user", "content": "hi"}], settings=settings_multi)
    assert res2.text == "recovered"
    assert res2.fallback_used is True
    assert 30.0 not in slept_durations, "Should not sleep for 30s; should skip immediately to next provider"
    assert providers_called == ["m1", "m2"]

