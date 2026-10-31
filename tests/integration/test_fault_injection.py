"""Integration tests for fault injection and graceful degradation."""

from datetime import datetime, timezone
import pytest

from core.cache import put
from core.config import get_settings
from core.errors import FeedError
from core.models import AOI
from core.pipeline import PipelineError, run_pipeline


@pytest.fixture(autouse=True)
def reset_settings_cache():
    """Ensure settings cache is fresh before and after every fault-injection test."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.mark.integration
def test_fault_injection_open_meteo(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test SIMULATE_API_FAILURE=open_meteo degrades with a warning and does not crash."""
    monkeypatch.setenv("SIMULATE_API_FAILURE", "open_meteo")
    get_settings.cache_clear()

    aoi = AOI(west=7.45, south=46.20, east=7.65, north=46.35)

    res = run_pipeline(
        aoi,
        mode="SCENARIO",
        ignition_point=aoi.center,
        bypass_cache=True,
    )

    assert res is not None
    assert res.wind.is_stale is True
    assert any("open-meteo" in w.lower() or "weather" in w.lower() for w in res.warnings), (
        f"Expected weather degradation warning in {res.warnings}"
    )


@pytest.mark.integration
def test_fault_injection_worldcover(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test SIMULATE_API_FAILURE=worldcover degrades to fallback fuel with a warning."""
    monkeypatch.setenv("SIMULATE_API_FAILURE", "worldcover")
    get_settings.cache_clear()

    aoi = AOI(west=7.45, south=46.20, east=7.65, north=46.35)

    res = run_pipeline(
        aoi,
        mode="SCENARIO",
        ignition_point=aoi.center,
        bypass_cache=True,
    )

    assert res is not None
    assert any("fuel" in w.lower() or "worldcover" in w.lower() or "landcover" in w.lower() for w in res.warnings), (
        f"Expected fuel/worldcover warning in {res.warnings}"
    )


@pytest.mark.integration
def test_fault_injection_overpass(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test SIMULATE_API_FAILURE=overpass raises structured FEED_DOWN error on fresh download."""
    monkeypatch.setenv("SIMULATE_API_FAILURE", "overpass")
    get_settings.cache_clear()

    # Fresh un-cached AOI
    aoi = AOI(west=-120.45, south=38.20, east=-120.35, north=38.30)

    with pytest.raises((PipelineError, FeedError)) as exc_info:
        run_pipeline(
            aoi,
            mode="SCENARIO",
            ignition_point=aoi.center,
            bypass_cache=True,
        )

    err = exc_info.value
    if isinstance(err, PipelineError):
        assert err.code in ("FEED_DOWN", "OSM_EMPTY")
    else:
        assert "Simulated Overpass API failure" in str(err) or "OpenStreetMap" in str(err)


@pytest.mark.integration
def test_fault_injection_firms_no_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test SIMULATE_API_FAILURE=firms raises FeedError / FEED_DOWN when no cache exists."""
    monkeypatch.setenv("SIMULATE_API_FAILURE", "firms")
    get_settings.cache_clear()

    aoi = AOI(west=-119.55, south=37.10, east=-119.45, north=37.20)

    with pytest.raises((PipelineError, FeedError)) as exc_info:
        run_pipeline(aoi, mode="LIVE", bypass_cache=True)

    err = exc_info.value
    if isinstance(err, PipelineError):
        assert err.code == "FEED_DOWN"
    else:
        assert "NASA FIRMS" in str(err) or "Simulated FIRMS" in str(err)


@pytest.mark.integration
def test_fault_injection_firms_stale_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test SIMULATE_API_FAILURE=firms serves stale cache with is_stale=True when cache exists."""
    aoi = AOI(west=7.45, south=46.20, east=7.65, north=46.35)
    key = f"firms:VIIRS_SNPP_NRT:{aoi.west:.4f},{aoi.south:.4f},{aoi.east:.4f},{aoi.north:.4f}:1"

    # Pre-populate disk cache with dummy detection CSV
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    sample_csv = f"latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,satellite,confidence,version,bright_ti5,frp,daynight\n46.28,7.55,340.0,0.4,0.4,{today_str},1200,N,nominal,2.0NRT,295.0,25.0,D\n".encode("utf-8")
    put(key=key, payload=sample_csv, source="NASA FIRMS", url="https://firms.modaps.eosdis.nasa.gov/api")

    monkeypatch.setenv("SIMULATE_API_FAILURE", "firms")
    get_settings.cache_clear()

    res = run_pipeline(aoi, mode="LIVE", bypass_cache=True)
    assert res is not None
    assert len(res.detections) > 0

    # Verify stale provenance record or warning
    has_stale_prov = any(p.is_stale for p in res.provenance if "FIRMS" in p.source.upper())
    has_stale_warn = any("stale" in w.lower() for w in res.warnings)
    assert has_stale_prov or has_stale_warn
