"""Unit tests for FIRMS CSV parser and deduplication logic."""

from datetime import datetime, timezone
import pytest
from core.data.firms import deduplicate_detections, parse_firms_csv
from core.errors import FeedError
from core.models import FireDetection

SAMPLE_VIIRS_CSV = """latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,satellite,instrument,confidence,version,bright_ti5,frp,daynight
38.15,-120.25,325.4,0.39,0.36,2026-10-31,0430,N,VIIRS,n,2.0NRT,290.1,15.2,N
38.16,-120.26,340.1,0.40,0.37,2026-10-31,0432,N,VIIRS,h,2.0NRT,295.4,42.8,N
38.17,-120.27,310.0,0.42,0.38,2026-10-31,0435,N,VIIRS,l,2.0NRT,285.0,4.1,N
38.18,-120.28,330.0,0.40,0.36,2026-10-25,0430,N,VIIRS,h,2.0NRT,290.0,20.0,N
"""

SAMPLE_MODIS_CSV = """latitude,longitude,brightness,scan,track,acq_date,acq_time,satellite,instrument,confidence,version,bright_t31,frp,daynight
37.50,-119.50,315.2,1.1,1.0,2026-10-31,1100,T,MODIS,85,6.1NRT,295.1,35.0,D
37.51,-119.51,305.0,1.1,1.0,2026-10-31,1105,T,MODIS,20,6.1NRT,290.0,10.0,D
"""


def test_parse_viirs_csv_filters_confidence_and_hours() -> None:
    """Test that low confidence ('l') and expired detections are filtered out."""
    now_ref = datetime(2026, 10, 31, 12, 0, 0, tzinfo=timezone.utc)
    dets = parse_firms_csv(SAMPLE_VIIRS_CSV, source="VIIRS_SNPP_NRT", hours=24, now_utc=now_ref)

    # 4 rows: row 1 ('n') kept, row 2 ('h') kept, row 3 ('l') excluded, row 4 (old date) excluded
    assert len(dets) == 2
    assert dets[0].confidence == "n"
    assert dets[0].frp == 15.2
    assert dets[0].acq_time_utc == datetime(2026, 10, 31, 4, 30, tzinfo=timezone.utc)

    assert dets[1].confidence == "h"
    assert dets[1].frp == 42.8


def test_parse_modis_csv_filters_confidence() -> None:
    """Test that MODIS confidence < 30 is excluded and >= 30 is retained."""
    now_ref = datetime(2026, 10, 31, 15, 0, 0, tzinfo=timezone.utc)
    dets = parse_firms_csv(SAMPLE_MODIS_CSV, source="MODIS_NRT", hours=24, now_utc=now_ref)

    # row 1 (85) kept, row 2 (20) excluded
    assert len(dets) == 1
    assert dets[0].frp == 35.0
    assert float(dets[0].confidence) == 85.0


def test_parse_empty_and_error_responses() -> None:
    """Test handling of empty responses and textual error bodies."""
    # Empty string returns empty list
    assert parse_firms_csv("", source="VIIRS_SNPP_NRT", hours=24) == []
    assert parse_firms_csv("latitude,longitude,acq_date,acq_time\n", source="VIIRS_SNPP_NRT", hours=24) == []

    # HTML error page raises FeedError
    with pytest.raises(FeedError, match="HTML error"):
        parse_firms_csv("<!DOCTYPE html><html><body>Error</body></html>", source="VIIRS_SNPP_NRT", hours=24)

    # Authorization text error raises FeedError
    with pytest.raises(FeedError, match="authorization error"):
        parse_firms_csv("Invalid MAP_KEY or transaction limit exceeded", source="VIIRS_SNPP_NRT", hours=24)


def test_deduplicate_detections() -> None:
    """Test deduplication of detections within 100m and 10 minutes."""
    t0 = datetime(2026, 10, 31, 10, 0, tzinfo=timezone.utc)
    t1 = datetime(2026, 10, 31, 10, 5, tzinfo=timezone.utc)  # +5 mins

    d1 = FireDetection(lat=38.0000, lon=-120.0000, acq_time_utc=t0, frp=15.0, confidence="n", satellite="N")
    d2 = FireDetection(lat=38.0002, lon=-120.0001, acq_time_utc=t1, frp=45.0, confidence="h", satellite="N20")  # ~25m away
    d3 = FireDetection(lat=38.0500, lon=-120.0500, acq_time_utc=t0, frp=20.0, confidence="n", satellite="N")  # >5km away

    deduped = deduplicate_detections([d1, d2, d3])
    # d1 and d2 duplicate each other; d2 has higher FRP (45.0 > 15.0) and should be kept
    assert len(deduped) == 2
    frps = {d.frp for d in deduped}
    assert 45.0 in frps
    assert 20.0 in frps
    assert 15.0 not in frps
