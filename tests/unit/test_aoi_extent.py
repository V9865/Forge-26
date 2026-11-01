"""Unit tests for AOI extent validation, IEEE 754 precision, and cluster splitting."""

import pytest
from pydantic import ValidationError
from datetime import datetime, timezone

from core.models import AOI, FireDetection
from core.data.firms import _split_oversized_clusters


def test_aoi_valid_dimensions():
    """Verify standard valid AOI within bounds."""
    aoi = AOI(west=-120.2, south=38.1, east=-119.8, north=38.5)
    assert aoi.west < aoi.east
    assert aoi.south < aoi.north
    assert round(aoi.east - aoi.west, 2) == 0.40
    assert round(aoi.north - aoi.south, 2) == 0.40


def test_aoi_floating_point_precision_boundary():
    """Verify that floating-point subtraction artifacts near 0.6000 are accepted with epsilon tolerance."""
    # 0.659 - 0.059 in IEEE 754 is 0.6000000000000001 (> 0.6)
    diff = 0.659 - 0.059
    assert diff > 0.6  # Demonstrates IEEE 754 floating-point artifact

    # AOI must accept this without raising validation error because of epsilon tolerance
    aoi = AOI(west=0.059, south=35.0, east=0.659, north=35.5)
    assert aoi.west == 0.059
    assert aoi.east == 0.659

    # Latitude axis check
    aoi_h = AOI(west=-120.0, south=0.059, east=-119.6, north=0.659)
    assert aoi_h.south == 0.059
    assert aoi_h.north == 0.659


def test_aoi_rejects_truly_oversized_extent():
    """Verify that AOIs exceeding 0.60 degrees (above tolerance) are strictly rejected."""
    with pytest.raises(ValidationError) as exc_info:
        AOI(west=0.0, south=0.0, east=0.6002, north=0.5)
    assert "exceeds maximum allowed 0.6°" in str(exc_info.value)

    with pytest.raises(ValidationError) as exc_info:
        AOI(west=0.0, south=0.0, east=0.5, north=0.6002)
    assert "exceeds maximum allowed 0.6°" in str(exc_info.value)


def test_aoi_rejects_inverted_or_flat_bounds():
    """Verify that inverted and degenerate zero-width bounds fail validation."""
    with pytest.raises(ValidationError):
        AOI(west=10.0, south=20.0, east=9.0, north=21.0)

    with pytest.raises(ValidationError):
        AOI(west=10.0, south=20.0, east=10.0, north=21.0)

    with pytest.raises(ValidationError):
        AOI(west=10.0, south=20.0, east=10.5, north=19.0)


def test_split_oversized_clusters_preserves_all_detections():
    """Verify that splitting oversized clusters partitions detections without dropping any."""
    now = datetime.now(timezone.utc)
    # Generate a wide cluster spanning 0.8 degrees in longitude
    wide_dets = [
        FireDetection(lat=35.0, lon=round(25.0 + i * 0.08, 4), acq_time_utc=now, frp=15.0, confidence="high", satellite="VIIRS")
        for i in range(11)  # 25.0 to 25.8
    ]
    span = max(d.lon for d in wide_dets) - min(d.lon for d in wide_dets)
    assert round(span, 2) == 0.8

    sub_clusters = _split_oversized_clusters(wide_dets, max_span_deg=0.44)
    assert len(sub_clusters) >= 2

    # Check conservation of detections
    total_split_dets = sum(len(c) for c in sub_clusters)
    assert total_split_dets == len(wide_dets)

    # Check each sub-cluster span is <= 0.44
    for sub in sub_clusters:
        span_lon = max(d.lon for d in sub) - min(d.lon for d in sub)
        span_lat = max(d.lat for d in sub) - min(d.lat for d in sub)
        assert span_lon <= 0.44 + 1e-7
        assert span_lat <= 0.44 + 1e-7
