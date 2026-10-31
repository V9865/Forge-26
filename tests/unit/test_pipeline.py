"""Unit tests for pipeline input validation, error handling, and result caching."""

import time
import pytest

from core.models import AOI, EvacParams, SpreadParams
from core.pipeline import (
    CACHE_TTL_SECONDS,
    PipelineError,
    _compute_input_hash,
    _validate_inputs,
    run_pipeline,
)


def test_aoi_extent_validation() -> None:
    """Test that AOI extents exceeding 0.6 degrees or invalid bounds raise GRID_TOO_LARGE or INVALID_INPUT."""
    # AOI too wide (> 0.6 degrees)
    with pytest.raises(PipelineError) as exc_info:
        aoi = AOI.model_construct(west=-120.8, south=38.0, east=-120.1, north=38.4)  # width 0.7
        _validate_inputs(aoi, mode="SCENARIO", ignition_point=None, wind_override=None)
    assert exc_info.value.code == "GRID_TOO_LARGE"

    # AOI west >= east
    with pytest.raises(PipelineError) as exc_info2:
        aoi = AOI.model_construct(west=-120.0, south=38.0, east=-120.5, north=38.4)
        _validate_inputs(aoi, mode="SCENARIO", ignition_point=None, wind_override=None)
    assert exc_info2.value.code == "INVALID_INPUT"


def test_ignition_point_inside_aoi_validation() -> None:
    """Test that scenario ignition outside AOI bounds raises INVALID_INPUT."""
    aoi = AOI(west=-120.5, south=38.0, east=-120.0, north=38.5)

    # Ignition point outside AOI
    with pytest.raises(PipelineError) as exc_info:
        _validate_inputs(aoi, mode="SCENARIO", ignition_point=(39.0, -120.2), wind_override=None)
    assert exc_info.value.code == "INVALID_INPUT"
    assert "outside AOI" in exc_info.value.message


def test_wind_override_range_validation() -> None:
    """Test that out-of-range wind speed or direction raises INVALID_INPUT."""
    aoi = AOI(west=-120.5, south=38.0, east=-120.0, north=38.5)

    # Speed > 40 m/s
    with pytest.raises(PipelineError) as exc_spd:
        _validate_inputs(aoi, mode="SCENARIO", ignition_point=(38.2, -120.2), wind_override={"speed_ms": 45.0})
    assert exc_spd.value.code == "INVALID_INPUT"
    assert "Wind speed" in exc_spd.value.message

    # Direction < 0 or > 360
    with pytest.raises(PipelineError) as exc_dir:
        _validate_inputs(aoi, mode="SCENARIO", ignition_point=(38.2, -120.2), wind_override={"dir_from_deg": 375.0})
    assert exc_dir.value.code == "INVALID_INPUT"
    assert "Wind direction" in exc_dir.value.message


def test_input_hash_and_caching() -> None:
    """Test that identical inputs produce identical hash and reuse cached results within 60s."""
    aoi = AOI(west=7.45, south=46.20, east=7.65, north=46.35)
    ign = (46.28, 7.55)
    wind = {"speed_ms": 5.0, "dir_from_deg": 270.0}

    h1 = _compute_input_hash(aoi, "SCENARIO", ign, wind, None, None)
    h2 = _compute_input_hash(aoi, "SCENARIO", ign, wind, None, None)
    assert h1 == h2

    # Different wind should produce different hash
    h3 = _compute_input_hash(aoi, "SCENARIO", ign, {"speed_ms": 8.0, "dir_from_deg": 270.0}, None, None)
    assert h1 != h3

