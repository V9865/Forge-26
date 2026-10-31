"""Unit tests for Open-Meteo JSON slicer and scenario overrides."""

from datetime import datetime, timezone
import pytest
from core.data.weather import _forward_fill_list, apply_override, slice_open_meteo_payload
from core.errors import FeedError
from core.models import WindSeries

SAMPLE_OPEN_METEO_JSON = {
    "hourly": {
        "time": [
            "2026-10-31T08:00",
            "2026-10-31T09:00",
            "2026-10-31T10:00",
            "2026-10-31T11:00",
            "2026-10-31T12:00",
            "2026-10-31T13:00",
        ],
        "wind_speed_10m": [4.0, 5.0, 6.0, None, 7.5, 8.0],
        "wind_direction_10m": [180.0, 190.0, 200.0, 210.0, 220.0, 230.0],
        "relative_humidity_2m": [40.0, 38.0, 35.0, 34.0, 32.0, 30.0],
        "temperature_2m": [22.0, 24.0, 26.0, 27.0, 28.0, 29.0],
    }
}


def test_slice_open_meteo_payload_at_current_hour() -> None:
    """Test slicing starting exactly at the requested UTC hour and forward-filling single gap."""
    ref_time = datetime(2026, 10, 31, 10, 25, tzinfo=timezone.utc)
    start_utc, speed, direction, rh, temp = slice_open_meteo_payload(
        SAMPLE_OPEN_METEO_JSON, hours_ahead=3, current_time_utc=ref_time
    )

    assert start_utc == datetime(2026, 10, 31, 10, 0, tzinfo=timezone.utc)
    assert len(speed) == 3
    assert len(direction) == 3

    # Index 10:00 is 6.0, Index 11:00 was None -> filled with 6.0, Index 12:00 is 7.5
    assert speed == [6.0, 6.0, 7.5]
    assert direction == [200.0, 210.0, 220.0]
    assert rh == [35.0, 34.0, 32.0]
    assert temp == [26.0, 27.0, 28.0]


def test_forward_fill_limit_and_errors() -> None:
    """Test forward-fill gap limits and error triggers."""
    # 2 consecutive None values allowed
    assert _forward_fill_list([10.0, None, None, 15.0], max_gap=2) == [10.0, 10.0, 10.0, 15.0]

    # 3 consecutive None values raises FeedError
    with pytest.raises(FeedError, match="gap of 3 exceeds allowable limit"):
        _forward_fill_list([10.0, None, None, None, 15.0], max_gap=2)

    # Leading None raises FeedError
    with pytest.raises(FeedError, match="Leading None"):
        _forward_fill_list([None, 10.0, 12.0], max_gap=2)


def test_apply_override() -> None:
    """Test scenario override modifying speed and direction with provenance flags."""
    series = WindSeries(
        start_utc=datetime(2026, 10, 31, 10, 0, tzinfo=timezone.utc),
        speed_ms=[4.0, 5.0, 6.0],
        dir_from_deg=[180.0, 190.0, 200.0],
        rh=[30.0, 30.0, 30.0],
        temp_c=[25.0, 25.0, 25.0],
        source="Open-Meteo",
        fetched_at_utc=datetime.now(timezone.utc),
        is_override=False,
    )

    overridden = apply_override(series, speed_ms=12.5, dir_from_deg=270.0)

    assert overridden.is_override is True
    assert overridden.source == "USER OVERRIDE (what-if)"
    assert overridden.speed_ms == [12.5, 12.5, 12.5]
    assert overridden.dir_from_deg == [270.0, 270.0, 270.0]
    # Original untouched
    assert series.is_override is False
    assert series.speed_ms == [4.0, 5.0, 6.0]

