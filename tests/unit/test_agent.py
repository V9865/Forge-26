"""Unit tests for briefing fact assembly and guardrail verification.

Tests:
- guard rejects a sentence with an invented number
- guard rejects an uncited sentence
- guard rejects an invented place name
- guard rejects a citation to a missing fact id
- guard accepts a correct sentence
- guard handles decimals and a range such as '30-40 minutes' correctly
- template_briefing mentions every TRAPPED settlement
- build_facts stays under the token cap with 60 synthetic settlements
- facts are deterministic for equal input
"""

from datetime import datetime, timezone
import numpy as np
import pytest

from core.agent.briefing import (
    briefing_messages,
    build_facts,
    facts_hash,
    template_briefing,
)
from core.agent.guard import verify
from core.geo import make_grid
from core.models import (
    AOI,
    GridSpec,
    PipelineResult,
    ProvenanceRecord,
    Settlement,
    SettlementPlan,
    SpreadParams,
    SpreadResult,
    WindSeries,
)


@pytest.fixture
def sample_facts():
    return {
        "F1": "Operational mode is LIVE using telemetry from NASA FIRMS, Open-Meteo, OpenStreetMap.",
        "F2": "Wind is 6.5 m/s from 270 degrees (W), source Open-Meteo, override False.",
        "F3": "Predicted burned area is 142.3 ha at 2 hours, 510.6 ha at 6 hours, and 1240.8 ha at 12 hours.",
        "F4": "Downwind fire spread direction is 90 degrees (E).",
        "F5": "Evacuation baseline: 3 of 5 threatened settlements have naive routes cut by fire, with 2 rescued by fire-aware replanning.",
        "F6": "Settlement Pine Ridge status is TRAPPED: fire arrival in 20 minutes, depart by 0 minutes, route travel time 35 minutes.",
        "F7": "Settlement Oak Valley status is EVACUATE: fire arrival in 45 minutes, depart by 25 minutes, route travel time 15 minutes.",
        "F8": "Data freshness: NASA FIRMS fetched 12 minutes ago, Open-Meteo fetched 8 minutes ago.",
    }


def test_guard_accepts_correct_sentence(sample_facts):
    text = (
        "Wind is blowing at 6.5 m/s from 270 degrees [F2]. "
        "Settlement Pine Ridge is TRAPPED with fire arrival in 20 minutes [F6]."
    )
    res = verify(text, sample_facts)
    assert res.ok is True
    assert res.dropped_count == 0
    assert "Wind is blowing at 6.5 m/s" in res.clean_text
    assert "Pine Ridge" in res.clean_text
    assert "[F2]" not in res.clean_text


def test_guard_rejects_uncited_sentence(sample_facts):
    text = (
        "Wind is blowing at 6.5 m/s from 270 degrees [F2]. "
        "Residents must remain calm and follow police directions. "
        "Settlement Oak Valley must depart within 25 minutes [F7]."
    )
    res = verify(text, sample_facts)
    # The uncited middle sentence must be dropped
    assert res.dropped_count == 1
    assert "Residents must remain calm" not in res.clean_text
    assert res.ok is True  # 2 valid sentences remain


def test_guard_rejects_invented_number(sample_facts):
    text = (
        "Wind is blowing at 99.9 m/s from 270 degrees [F2]. "
        "Settlement Oak Valley must depart within 25 minutes [F7]."
    )
    res = verify(text, sample_facts)
    # 99.9 is not in F2
    assert res.dropped_count == 1
    assert "99.9" not in res.clean_text
    assert res.ok is False  # Only 1 sentence survived


def test_guard_rejects_invented_place_name(sample_facts):
    text = (
        "Settlement Beverly Hills is under an EVACUATE order with arrival in 45 minutes [F7]. "
        "Settlement Pine Ridge is TRAPPED with arrival in 20 minutes [F6]."
    )
    res = verify(text, sample_facts)
    # Beverly Hills is not in F7
    assert res.dropped_count == 1
    assert "Beverly Hills" not in res.clean_text
    assert "Pine Ridge" in res.clean_text


def test_guard_rejects_citation_to_missing_fact_id(sample_facts):
    text = (
        "Wind is 6.5 m/s from 270 degrees [F99]. "
        "Settlement Oak Valley must depart within 25 minutes [F7]."
    )
    res = verify(text, sample_facts)
    # F99 does not exist in sample_facts
    assert res.dropped_count == 1
    assert "6.5 m/s" not in res.clean_text
    assert res.ok is False


def test_guard_handles_decimals_and_ranges():
    """Document and test range and decimal handling in guardrail verification.

    Range Handling Specification:
    Ranges such as '30-40 minutes' or '30 to 40 min' are decomposed into individual
    numeric tokens ('30' and '40'). Both numbers must be substantiated in cited facts.
    """
    facts = {
        "F1": "Fire travel time is between 30 and 40 minutes for Ridge Crest.",
        "F2": "Predicted burned area is 142.3 ha at 2 hours.",
        "F3": "Evacuation deadline is 50 minutes.",
    }

    # Valid range and decimal
    valid_text = (
        "Travel time for Ridge Crest is approximately 30-40 minutes [F1]. "
        "The predicted burned area reached 142.3 ha [F2]."
    )
    res_valid = verify(valid_text, facts)
    assert res_valid.ok is True
    assert res_valid.dropped_count == 0
    assert "30-40 minutes" in res_valid.clean_text
    assert "142.3 ha" in res_valid.clean_text

    # Range containing an invented number (e.g. 30-95 where 95 is not in F1)
    invalid_range_text = (
        "Travel time is 30-95 minutes [F1]. "
        "The predicted burned area reached 142.3 ha [F2]."
    )
    res_invalid = verify(invalid_range_text, facts)
    assert res_invalid.dropped_count == 1
    assert "30-95" not in res_invalid.clean_text


def test_template_briefing_mentions_every_trapped_settlement():
    facts = {
        "F1": "Wind is 5.0 m/s from 180 degrees (S), source Open-Meteo, override False.",
        "F2": "Settlement Alpha is TRAPPED: fire arrival in 10 minutes, depart by 0 minutes, route travel time 20 minutes.",
        "F3": "Settlement Beta is TRAPPED: fire arrival in 15 minutes, depart by 0 minutes, route travel time 25 minutes.",
        "F4": "Settlement Gamma status is EVACUATE: fire arrival in 30 minutes, depart by 10 minutes, route travel time 15 minutes.",
        "F5": "Data freshness: NASA FIRMS fetched 5 minutes ago.",
    }
    tb = template_briefing(facts)
    assert "Alpha is TRAPPED" in tb
    assert "Beta is TRAPPED" in tb
    assert "Gamma status is EVACUATE" in tb
    assert "Wind is 5.0 m/s" in tb
    assert "Data freshness:" in tb


def test_build_facts_stays_under_token_cap_with_60_synthetic_settlements():
    """Verify build_facts caps output to at most 25 facts and <= 1200 tokens with 60 settlements."""
    t0 = datetime(2026, 10, 25, 12, 0, tzinfo=timezone.utc)
    aoi = AOI(west=-120.5, south=38.0, east=-120.0, north=38.5)
    grid = make_grid(aoi, res_m=100.0, max_cells=1000000)
    arr = np.full((grid.ny, grid.nx), 500.0, dtype=np.float32)

    spread = SpreadResult(
        grid=grid,
        arrival_min=arr,
        ignitions=[(38.25, -120.25)],
        params=SpreadParams(),
        runtime_s=0.05,
    )
    wind = WindSeries(
        start_utc=t0,
        speed_ms=[5.0] * 24,
        dir_from_deg=[270.0] * 24,
        rh=[30.0] * 24,
        temp_c=[25.0] * 24,
        source="Open-Meteo",
        fetched_at_utc=t0,
    )

    plans: list[SettlementPlan] = []
    # 5 TRAPPED settlements
    for i in range(5):
        s = Settlement(id=f"trap_{i}", name=f"TrappedTown_{i}", lat=38.1 + i * 0.05, lon=-120.4)
        plans.append(
            SettlementPlan(
                settlement=s,
                status="TRAPPED",
                fire_arrival_min=10.0 + i,
                depart_by_min=0.0,
                route_travel_min=30.0,
            )
        )
    # 55 EVACUATE settlements with various deadlines
    for i in range(55):
        s = Settlement(id=f"evac_{i}", name=f"EvacTown_{i:02d}", lat=38.05 + (i % 20) * 0.02, lon=-120.3)
        plans.append(
            SettlementPlan(
                settlement=s,
                status="EVACUATE",
                fire_arrival_min=30.0 + i * 2,
                depart_by_min=15.0 + i * 2,
                route_travel_min=12.0,
            )
        )

    prov = [
        ProvenanceRecord(name="firms", source="NASA FIRMS", url="http://firms", fetched_at_utc=t0, ttl_s=900),
        ProvenanceRecord(name="meteo", source="Open-Meteo", url="http://meteo", fetched_at_utc=t0, ttl_s=600),
    ]

    pipeline_res = PipelineResult(
        aoi=aoi,
        mode="LIVE",
        detections=[],
        wind=wind,
        spread=spread,
        plans=plans,
        metrics={"n_threatened": 60, "n_naive_cut": 45, "n_rescued_by_replan": 30},
        provenance=prov,
        warnings=["Fuel layer degraded to static fallback."],
    )

    facts = build_facts(pipeline_res)

    # Invariants
    assert len(facts) <= 25, f"Expected <= 25 facts, got {len(facts)}"
    total_tokens = sum(len(text) // 4 for text in facts.values())
    assert total_tokens <= 1200, f"Expected <= 1200 tokens, got {total_tokens}"

    # Every TRAPPED settlement must be included
    for i in range(5):
        assert any(f"TrappedTown_{i}" in f for f in facts.values()), f"TrappedTown_{i} missing!"


def test_facts_are_deterministic_for_equal_input():
    t0 = datetime(2026, 10, 25, 12, 0, tzinfo=timezone.utc)
    aoi = AOI(west=-120.5, south=38.0, east=-120.0, north=38.5)
    grid = make_grid(aoi, res_m=100.0, max_cells=1000000)
    arr = np.full((grid.ny, grid.nx), 100.0, dtype=np.float32)

    spread = SpreadResult(grid=grid, arrival_min=arr, ignitions=[], params=SpreadParams(), runtime_s=0.01)
    wind = WindSeries(
        start_utc=t0,
        speed_ms=[4.0],
        dir_from_deg=[180.0],
        rh=[40.0],
        temp_c=[20.0],
        source="Open-Meteo",
        fetched_at_utc=t0,
    )
    s = Settlement(id="s1", name="Pine Valley", lat=38.1, lon=-120.1)
    plan = SettlementPlan(
        settlement=s,
        status="EVACUATE",
        fire_arrival_min=45.0,
        depart_by_min=20.0,
        route_travel_min=15.0,
    )
    prov = [ProvenanceRecord(name="firms", source="NASA FIRMS", url="http://f", fetched_at_utc=t0, ttl_s=900)]

    res1 = PipelineResult(
        aoi=aoi,
        mode="LIVE",
        detections=[],
        wind=wind,
        spread=spread,
        plans=[plan],
        metrics={"n_threatened": 1, "n_naive_cut": 1, "n_rescued_by_replan": 1},
        provenance=prov,
        warnings=[],
    )
    res2 = PipelineResult(
        aoi=aoi,
        mode="LIVE",
        detections=[],
        wind=wind,
        spread=spread,
        plans=[plan],
        metrics={"n_threatened": 1, "n_naive_cut": 1, "n_rescued_by_replan": 1},
        provenance=prov,
        warnings=[],
    )

    facts1 = build_facts(res1)
    facts2 = build_facts(res2)

    assert facts1 == facts2
    assert facts_hash(facts1) == facts_hash(facts2)


def test_briefing_messages_prompt_format(sample_facts):
    msgs = briefing_messages(sample_facts)
    assert len(msgs) == 2
    assert msgs[0]["role"] == "system"
    assert "Write a 5 to 8 sentence operational briefing" in msgs[0]["content"]
    assert msgs[1]["role"] == "user"
    assert "F1:" in msgs[1]["content"]
    assert "F6:" in msgs[1]["content"]
