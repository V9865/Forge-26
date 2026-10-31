"""Unit tests for disk caching, TTL expiration, and stale fallback."""

import shutil
import tempfile
import time
import pytest
from core import cache
from core.errors import FeedError, StaleCacheWarning


@pytest.fixture(autouse=True)
def temp_cache_dir(monkeypatch: pytest.MonkeyPatch, tmp_path):
    """Use a temporary directory for cache operations in each test."""
    monkeypatch.setenv("CACHE_DIR", str(tmp_path / "test_cache"))
    # Clear settings lru_cache so CACHE_DIR takes effect
    from core.config import get_settings
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_cache_ttl_expiry() -> None:
    """Test fresh retrieval within TTL and expiration after TTL."""
    key = "firms:test_aoi"
    payload = b'{"detections": 42}'
    source = "NASA FIRMS"
    url = "https://firms.modaps.eosdis.nasa.gov/api/area"

    # Store payload
    record = cache.put(key, payload, source, url)
    assert record.name == key
    assert record.source == source
    assert record.is_stale is False

    # Within TTL (fresh)
    data, meta = cache.get(key, ttl_s=3600)
    assert data == payload
    assert meta is not None
    assert meta.is_stale is False

    # Expired TTL
    expired_data, expired_meta = cache.get(key, ttl_s=-1)
    assert expired_data is None
    assert expired_meta is not None
    assert expired_meta.is_stale is True


def test_stale_fallback_when_fetch_raises_feed_error() -> None:
    """Test that cached_or_fetch returns stale cache with warning on FeedError."""
    key = "weather:current"
    initial_payload = b'{"temp": 25.0, "wind_speed": 12.0}'
    source = "Open-Meteo"
    url = "https://api.open-meteo.com/v1/forecast"

    # Seed disk cache
    cache.put(key, initial_payload, source, url)

    def failing_fetch():
        raise FeedError(
            message="Connection timed out",
            source="Open-Meteo",
            url=url,
        )

    # Calling with ttl_s=0 forces re-fetch, which fails.
    # Should fall back to stale cache with StaleCacheWarning
    with pytest.warns(StaleCacheWarning, match="Live fetch failed"):
        data, record = cache.cached_or_fetch(
            key=key,
            ttl_s=0,
            fetch_fn=failing_fetch,
            allow_stale=True,
        )

    assert data == initial_payload
    assert record.is_stale is True
    assert record.source == "Open-Meteo" or record.source == "disk_cache"
    assert "stale" in record.note.lower()


def test_reraise_when_no_cache_exists() -> None:
    """Test that FeedError is re-raised when no cached data exists."""
    key = "unknown_feed_key"

    def failing_fetch():
        raise FeedError(
            message="404 Not Found",
            source="ESA WorldCover",
            url="https://services.terrascope.be/wms",
        )

    with pytest.raises(FeedError, match="404 Not Found"):
        cache.cached_or_fetch(
            key=key,
            ttl_s=60,
            fetch_fn=failing_fetch,
            allow_stale=True,
        )


def test_cached_or_fetch_success_flow() -> None:
    """Test successful network fetch when cache is empty."""
    key = "dynamic:feed"
    fresh_payload = b'{"status": "ok"}'

    def successful_fetch():
        return (fresh_payload, "CustomFeed", "https://api.custom.org")

    data, record = cache.cached_or_fetch(key, ttl_s=60, fetch_fn=successful_fetch)
    assert data == fresh_payload
    assert record.is_stale is False
    assert record.source == "CustomFeed"

    # Second fetch should hit cache without calling fetch_fn
    def should_not_run():
        raise AssertionError("fetch_fn was called unexpectedly")

    cached_data, cached_record = cache.cached_or_fetch(key, ttl_s=60, fetch_fn=should_not_run)
    assert cached_data == fresh_payload
    assert cached_record.is_stale is False
