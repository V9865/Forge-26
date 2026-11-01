"""External data feed health and connectivity verification module.

Checks live endpoints for:
- NASA FIRMS (API key status and sample area query)
- Open-Meteo (Forecast API query)
- AWS Terrarium elevation tiles
- ESA WorldCover land cover tiles
- OpenStreetMap Overpass API
Never fails the entire health check if an individual feed encounters an error.
"""

from datetime import datetime, timezone
import logging
import time
from typing import Any, Dict
import httpx

from core.config import get_settings

logger = logging.getLogger(__name__)


def _check_firms(timeout_s: float) -> Dict[str, Any]:
    """Check NASA FIRMS key status and query capability."""
    settings = get_settings()
    map_key = settings.FIRMS_MAP_KEY.strip()

    if not map_key:
        return {
            "ok": False,
            "latency_ms": 0.0,
            "detail": "FIRMS_MAP_KEY is not configured in .env",
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }

    t0 = time.time()
    try:
        # Check key status endpoint
        status_url = f"https://firms.modaps.eosdis.nasa.gov/mapserver/mapkey_status/?MAP_KEY={map_key}"
        with httpx.Client(timeout=timeout_s) as client:
            resp = client.get(status_url)
            latency_ms = round((time.time() - t0) * 1000.0, 1)

            if resp.status_code == 200:
                body_text = resp.text.strip().lower()
                if "invalid" in body_text or "exceeded" in body_text:
                    return {
                        "ok": False,
                        "latency_ms": latency_ms,
                        "detail": f"FIRMS key rejected: {resp.text[:80]}",
                        "fetched_at": datetime.now(timezone.utc).isoformat(),
                    }

                # Secondary check: tiny area query
                area_url = f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/{map_key}/VIIRS_SNPP_NRT/-120.1,38.1,-120.0,38.2/1"
                area_resp = client.get(area_url)
                if area_resp.status_code == 200 and not area_resp.text.strip().lower().startswith("<!doctype"):
                    return {
                        "ok": True,
                        "latency_ms": latency_ms,
                        "detail": "FIRMS API key valid and area endpoint accessible",
                        "fetched_at": datetime.now(timezone.utc).isoformat(),
                    }
                else:
                    return {
                        "ok": False,
                        "latency_ms": latency_ms,
                        "detail": f"FIRMS area query error: {area_resp.text[:80]}",
                        "fetched_at": datetime.now(timezone.utc).isoformat(),
                    }

            return {
                "ok": False,
                "latency_ms": latency_ms,
                "detail": f"HTTP {resp.status_code}: {resp.text[:80]}",
                "fetched_at": datetime.now(timezone.utc).isoformat(),
            }
    except Exception as e:
        latency_ms = round((time.time() - t0) * 1000.0, 1)
        return {
            "ok": False,
            "latency_ms": latency_ms,
            "detail": f"Connection error: {str(e)}",
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }


def _check_open_meteo(timeout_s: float) -> Dict[str, Any]:
    """Check Open-Meteo forecast API availability."""
    url = "https://api.open-meteo.com/v1/forecast?latitude=38.0&longitude=-120.0&hourly=temperature_2m&forecast_days=1"
    t0 = time.time()
    try:
        with httpx.Client(timeout=timeout_s) as client:
            resp = client.get(url)
            latency_ms = round((time.time() - t0) * 1000.0, 1)
            if resp.status_code == 200:
                return {
                    "ok": True,
                    "latency_ms": latency_ms,
                    "detail": "Open-Meteo forecast endpoint operational",
                    "fetched_at": datetime.now(timezone.utc).isoformat(),
                }
            return {
                "ok": False,
                "latency_ms": latency_ms,
                "detail": f"HTTP {resp.status_code}",
                "fetched_at": datetime.now(timezone.utc).isoformat(),
            }
    except Exception as e:
        latency_ms = round((time.time() - t0) * 1000.0, 1)
        return {
            "ok": False,
            "latency_ms": latency_ms,
            "detail": f"Connection error: {str(e)}",
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }


def _check_terrarium(timeout_s: float) -> Dict[str, Any]:
    """Check AWS Terrarium elevation tile endpoint."""
    url = "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/10/163/395.png"
    t0 = time.time()
    try:
        with httpx.Client(timeout=timeout_s) as client:
            resp = client.get(url)
            latency_ms = round((time.time() - t0) * 1000.0, 1)
            if resp.status_code == 200 and resp.headers.get("content-type", "").startswith("image/"):
                return {
                    "ok": True,
                    "latency_ms": latency_ms,
                    "detail": "AWS Terrarium elevation tiles operational",
                    "fetched_at": datetime.now(timezone.utc).isoformat(),
                }
            return {
                "ok": False,
                "latency_ms": latency_ms,
                "detail": f"Unexpected status {resp.status_code}",
                "fetched_at": datetime.now(timezone.utc).isoformat(),
            }
    except Exception as e:
        latency_ms = round((time.time() - t0) * 1000.0, 1)
        return {
            "ok": False,
            "latency_ms": latency_ms,
            "detail": f"Connection error: {str(e)}",
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }


def _check_worldcover(timeout_s: float) -> Dict[str, Any]:
    """Check ESA WorldCover tile accessibility."""
    url = "https://esa-worldcover.s3.eu-central-1.amazonaws.com/v100/2020/map/ESA_WorldCover_10m_2020_v100_N36W120_Map.tif"
    t0 = time.time()
    try:
        headers = {"Range": "bytes=0-100"}
        with httpx.Client(timeout=timeout_s) as client:
            resp = client.get(url, headers=headers)
            latency_ms = round((time.time() - t0) * 1000.0, 1)
            if resp.status_code in (200, 206):
                return {
                    "ok": True,
                    "latency_ms": latency_ms,
                    "detail": "ESA WorldCover S3 storage operational",
                    "fetched_at": datetime.now(timezone.utc).isoformat(),
                }
            return {
                "ok": False,
                "latency_ms": latency_ms,
                "detail": f"HTTP {resp.status_code}",
                "fetched_at": datetime.now(timezone.utc).isoformat(),
            }
    except Exception as e:
        latency_ms = round((time.time() - t0) * 1000.0, 1)
        return {
            "ok": False,
            "latency_ms": latency_ms,
            "detail": f"Connection error: {str(e)}",
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }


def _check_overpass(timeout_s: float) -> Dict[str, Any]:
    """Check OpenStreetMap Overpass API server status, falling back to OSM API capabilities."""
    endpoints = [
        "https://overpass-api.de/api/status",
        "https://lz4.overpass-api.de/api/status",
        "https://api.openstreetmap.org/api/0.6/capabilities",
    ]
    headers = {"User-Agent": "EmberRoute/0.1.0 (wildfire-planner)"}
    t0 = time.time()

    for endpoint in endpoints:
        try:
            with httpx.Client(timeout=min(3.0, timeout_s)) as client:
                resp = client.get(endpoint, headers=headers)
                latency_ms = round((time.time() - t0) * 1000.0, 1)
                if resp.status_code == 200:
                    body = resp.text.lower()
                    if "connected as" in body or "openstreetmap" in body:
                        return {
                            "ok": True,
                            "latency_ms": latency_ms,
                            "detail": f"OpenStreetMap API operational ({endpoint})",
                            "fetched_at": datetime.now(timezone.utc).isoformat(),
                        }
        except Exception:
            continue

    latency_ms = round((time.time() - t0) * 1000.0, 1)
    return {
        "ok": False,
        "latency_ms": latency_ms,
        "detail": "All Overpass/OSM endpoints timed out or failed",
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }


def check_all() -> Dict[str, Dict[str, Any]]:
    """Probe all external live data sources and return health report dictionary.

    Returns:
        Dict mapping feed_name to {ok: bool, latency_ms: float, detail: str, fetched_at: str}.
    """
    settings = get_settings()
    timeout = min(4.0, float(settings.HTTP_TIMEOUT_S))

    return {
        "firms": _check_firms(timeout_s=timeout),
        "open_meteo": _check_open_meteo(timeout_s=timeout),
        "terrarium": _check_terrarium(timeout_s=timeout),
        "worldcover": _check_worldcover(timeout_s=timeout),
        "overpass": _check_overpass(timeout_s=timeout),
    }
