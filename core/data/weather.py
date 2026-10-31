"""Open-Meteo weather and wind series ingestion module.

Fetches live and historical meteorological conditions (wind speed, wind direction,
relative humidity, temperature) from Open-Meteo API.
Wind direction convention: direction wind blows FROM in degrees [0, 360) clockwise from North.
"""

from datetime import datetime, timezone
import json
import logging
from typing import Any, Dict, List, Optional, Tuple
import httpx

from core.cache import cached_or_fetch
from core.config import get_settings
from core.errors import FeedError
from core.models import ProvenanceRecord, WindSeries

logger = logging.getLogger(__name__)

OPEN_METEO_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
OPEN_METEO_ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"


def _forward_fill_list(values: List[Optional[float]], max_gap: int = 2) -> List[float]:
    """Forward-fill missing (None) values in a series up to max_gap consecutive elements.

    Args:
        values: List containing float values or None.
        max_gap: Maximum number of consecutive None values permitted.

    Returns:
        List of filled float values.

    Raises:
        FeedError: If gaps exceed max_gap or leading elements are None.
    """
    if not values:
        return []

    filled: List[float] = []
    consecutive_none = 0

    for i, val in enumerate(values):
        if val is not None:
            filled.append(float(val))
            consecutive_none = 0
        else:
            consecutive_none += 1
            if consecutive_none > max_gap:
                raise FeedError(
                    f"Weather series gap of {consecutive_none} exceeds allowable limit of {max_gap}",
                    source="Open-Meteo",
                )
            if not filled:
                raise FeedError(
                    "Leading None value in weather series cannot be forward-filled",
                    source="Open-Meteo",
                )
            filled.append(filled[-1])

    return filled


def slice_open_meteo_payload(
    payload_dict: Dict[str, Any], hours_ahead: int, current_time_utc: Optional[datetime] = None
) -> Tuple[datetime, List[float], List[float], List[float], List[float]]:
    """Slice and sanitize raw Open-Meteo JSON payload starting from current UTC hour.

    Args:
        payload_dict: Parsed JSON dictionary from Open-Meteo response.
        hours_ahead: Minimum required duration in hours.
        current_time_utc: Reference UTC datetime (defaults to now).

    Returns:
        Tuple of (start_utc, speed_ms, dir_from_deg, rh, temp_c).

    Raises:
        FeedError: If hourly data is missing, incomplete, or contains unfillable gaps.
    """
    hourly = payload_dict.get("hourly")
    if not isinstance(hourly, dict) or "time" not in hourly:
        raise FeedError("Malformed Open-Meteo response: missing 'hourly.time'", source="Open-Meteo")

    time_strs = hourly.get("time", [])
    if not time_strs:
        raise FeedError("Empty time array in Open-Meteo response", source="Open-Meteo")

    if current_time_utc is None:
        current_time_utc = datetime.now(timezone.utc)

    # Truncate reference time to top of current UTC hour
    ref_hour = current_time_utc.replace(minute=0, second=0, microsecond=0)
    ref_hour_str = ref_hour.strftime("%Y-%m-%dT%H:00")

    # Find starting index corresponding to current hour
    start_idx = -1
    for i, t in enumerate(time_strs):
        if t == ref_hour_str:
            start_idx = i
            break

    # If exact hour not found, find the first timestamp >= ref_hour
    if start_idx == -1:
        for i, t in enumerate(time_strs):
            if t >= ref_hour_str:
                start_idx = i
                break

    if start_idx == -1:
        raise FeedError(
            f"Current hour {ref_hour_str} not found in Open-Meteo forecast range",
            source="Open-Meteo",
        )

    end_idx = start_idx + hours_ahead
    available_len = len(time_strs) - start_idx
    if available_len < hours_ahead:
        raise FeedError(
            f"Insufficient forecast hours: available {available_len} < requested {hours_ahead}",
            source="Open-Meteo",
        )

    raw_speed = hourly.get("wind_speed_10m", [])[start_idx:end_idx]
    raw_dir = hourly.get("wind_direction_10m", [])[start_idx:end_idx]
    raw_rh = hourly.get("relative_humidity_2m", [])[start_idx:end_idx]
    raw_temp = hourly.get("temperature_2m", [])[start_idx:end_idx]

    speed_ms = _forward_fill_list(raw_speed, max_gap=2)
    dir_from_deg = _forward_fill_list(raw_dir, max_gap=2)
    rh = _forward_fill_list(raw_rh, max_gap=2)
    temp_c = _forward_fill_list(raw_temp, max_gap=2)

    start_utc = datetime.fromisoformat(time_strs[start_idx]).replace(tzinfo=timezone.utc)
    return start_utc, speed_ms, dir_from_deg, rh, temp_c


def fetch_wind_series(
    lat: float, lon: float, hours_ahead: int = 24
) -> Tuple[WindSeries, ProvenanceRecord]:
    """Fetch live hourly wind and atmospheric series for a location from Open-Meteo.

    Args:
        lat: Latitude in decimal degrees (-90 to 90).
        lon: Longitude in decimal degrees (-180 to 180).
        hours_ahead: Forecast horizon in hours (default 24).

    Returns:
        Tuple of (WindSeries, ProvenanceRecord).

    Raises:
        FeedError: On network, HTTP, or data validation error.
    """
    settings = get_settings()

    if settings.SIMULATE_API_FAILURE == "open_meteo":
        raise FeedError("Simulated Open-Meteo feed failure", source="Open-Meteo")

    query_params = {
        "latitude": f"{lat:.4f}",
        "longitude": f"{lon:.4f}",
        "hourly": "wind_speed_10m,wind_direction_10m,wind_gusts_10m,relative_humidity_2m,temperature_2m",
        "wind_speed_unit": "ms",
        "timezone": "UTC",
        "past_days": 1,
        "forecast_days": 2,
    }

    url_with_params = httpx.URL(OPEN_METEO_FORECAST_URL, params=query_params)
    request_url = str(url_with_params)
    cache_key = f"openmeteo:forecast:{lat:.4f},{lon:.4f}"

    def _do_fetch() -> Tuple[bytes, str, str]:
        logger.info("Fetching Open-Meteo forecast from %s", request_url)
        with httpx.Client(timeout=settings.HTTP_TIMEOUT_S) as client:
            resp = client.get(request_url)
            if resp.status_code != 200:
                raise FeedError(
                    f"HTTP {resp.status_code} from Open-Meteo: {resp.text[:100]}",
                    source="Open-Meteo",
                    url=request_url,
                )
            return resp.content, "Open-Meteo", request_url

    content_bytes, prov = cached_or_fetch(
        key=cache_key,
        ttl_s=settings.WEATHER_TTL_S,
        fetch_fn=_do_fetch,
        allow_stale=True,
    )

    try:
        payload_dict = json.loads(content_bytes.decode("utf-8"))
    except Exception as e:
        raise FeedError(f"Failed to parse Open-Meteo JSON payload: {e}", source="Open-Meteo")

    start_utc, speed_ms, dir_from_deg, rh, temp_c = slice_open_meteo_payload(
        payload_dict=payload_dict,
        hours_ahead=hours_ahead,
    )

    series = WindSeries(
        start_utc=start_utc,
        speed_ms=speed_ms,
        dir_from_deg=dir_from_deg,
        rh=rh,
        temp_c=temp_c,
        source="Open-Meteo",
        fetched_at_utc=prov.fetched_at_utc,
        is_override=False,
        is_stale=prov.is_stale,
    )
    return series, prov


def apply_override(
    series: WindSeries,
    speed_ms: Optional[float] = None,
    dir_from_deg: Optional[float] = None,
) -> WindSeries:
    """Create a scenario override copy of a WindSeries.

    Args:
        series: Original live WindSeries.
        speed_ms: Optional uniform wind speed override in m/s.
        dir_from_deg: Optional uniform wind direction override in degrees from North.

    Returns:
        Modified WindSeries flagged with is_override=True and source='USER OVERRIDE (what-if)'.
    """
    n = len(series.speed_ms)
    new_speeds = [float(speed_ms)] * n if speed_ms is not None else list(series.speed_ms)
    new_dirs = [float(dir_from_deg)] * n if dir_from_deg is not None else list(series.dir_from_deg)

    return WindSeries(
        start_utc=series.start_utc,
        speed_ms=new_speeds,
        dir_from_deg=new_dirs,
        rh=list(series.rh),
        temp_c=list(series.temp_c),
        source="USER OVERRIDE (what-if)",
        fetched_at_utc=series.fetched_at_utc,
        is_override=True,
        is_stale=series.is_stale,
    )


def fetch_wind_history(
    lat: float, lon: float, start_date: str, end_date: str
) -> Tuple[WindSeries, ProvenanceRecord]:
    """Fetch historical wind and weather conditions from Open-Meteo Archive for model validation.

    Args:
        lat: Latitude in degrees.
        lon: Longitude in degrees.
        start_date: Start date string (YYYY-MM-DD).
        end_date: End date string (YYYY-MM-DD).

    Returns:
        Tuple of (WindSeries, ProvenanceRecord).
    """
    settings = get_settings()

    query_params = {
        "latitude": f"{lat:.4f}",
        "longitude": f"{lon:.4f}",
        "start_date": start_date,
        "end_date": end_date,
        "hourly": "wind_speed_10m,wind_direction_10m,wind_gusts_10m,relative_humidity_2m,temperature_2m",
        "wind_speed_unit": "ms",
        "timezone": "UTC",
    }

    url_with_params = httpx.URL(OPEN_METEO_ARCHIVE_URL, params=query_params)
    request_url = str(url_with_params)
    cache_key = f"openmeteo:archive:{lat:.4f},{lon:.4f}:{start_date}_{end_date}"

    def _do_fetch() -> Tuple[bytes, str, str]:
        with httpx.Client(timeout=settings.HTTP_TIMEOUT_S) as client:
            resp = client.get(request_url)
            if resp.status_code != 200:
                raise FeedError(
                    f"HTTP {resp.status_code} from Open-Meteo Archive: {resp.text[:100]}",
                    source="Open-Meteo",
                    url=request_url,
                )
            return resp.content, "Open-Meteo Archive", request_url

    # Archive data is static, use static TTL (24h)
    content_bytes, prov = cached_or_fetch(
        key=cache_key,
        ttl_s=settings.cache_ttl_static if hasattr(settings, "cache_ttl_static") else 86400,
        fetch_fn=_do_fetch,
        allow_stale=True,
    )

    payload_dict = json.loads(content_bytes.decode("utf-8"))
    hourly = payload_dict.get("hourly", {})
    time_strs = hourly.get("time", [])

    if not time_strs:
        raise FeedError("Empty archive history returned", source="Open-Meteo Archive")

    speed_ms = _forward_fill_list(hourly.get("wind_speed_10m", []), max_gap=2)
    dir_from_deg = _forward_fill_list(hourly.get("wind_direction_10m", []), max_gap=2)
    rh = _forward_fill_list(hourly.get("relative_humidity_2m", []), max_gap=2)
    temp_c = _forward_fill_list(hourly.get("temperature_2m", []), max_gap=2)

    start_utc = datetime.fromisoformat(time_strs[0]).replace(tzinfo=timezone.utc)

    series = WindSeries(
        start_utc=start_utc,
        speed_ms=speed_ms,
        dir_from_deg=dir_from_deg,
        rh=rh,
        temp_c=temp_c,
        source="Open-Meteo Archive",
        fetched_at_utc=prov.fetched_at_utc,
        is_override=False,
        is_stale=prov.is_stale,
    )
    return series, prov

