"""Integration tests asserting schema compliance against live upstream APIs."""

import pytest
from core.config import get_settings
from core.data.firms import fetch_detections
from core.data.weather import fetch_wind_series
from core.models import AOI, FireDetection, WindSeries


@pytest.mark.integration
def test_live_open_meteo_forecast() -> None:
    """Fetch live forecast from Open-Meteo for a test coordinate in California."""
    lat, lon = 38.0, -120.0
    series, prov = fetch_wind_series(lat=lat, lon=lon, hours_ahead=12)

    assert isinstance(series, WindSeries)
    assert len(series.speed_ms) == 12
    assert len(series.dir_from_deg) == 12
    assert len(series.rh) == 12
    assert len(series.temp_c) == 12
    assert series.source == "Open-Meteo"
    assert prov.source == "Open-Meteo"
    assert prov.is_stale is False


@pytest.mark.integration
def test_live_firms_detections() -> None:
    """Fetch live FIRMS detections if FIRMS_MAP_KEY is configured."""
    settings = get_settings()
    if not settings.FIRMS_MAP_KEY:
        pytest.skip("FIRMS_MAP_KEY not configured, skipping live FIRMS integration test")

    aoi = AOI(west=-120.2, south=38.1, east=-120.0, north=38.3)
    dets, prov = fetch_detections(aoi=aoi, hours=24)

    assert isinstance(dets, list)
    for d in dets:
        assert isinstance(d, FireDetection)
        assert -120.2 <= d.lon <= -120.0
        assert 38.1 <= d.lat <= 38.3
    assert prov.source == "NASA FIRMS"
