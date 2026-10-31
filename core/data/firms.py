"""NASA FIRMS live fire detection and active cluster ingestion module.

Fetches near-real-time satellite fire observations from VIIRS and MODIS sensors.
Complies with non-negotiable data rules:
- No dummy/mock data.
- Masks MAP_KEY in all logs and provenance records.
- Raises FeedError on network or parsing failure.
"""

from datetime import datetime, timedelta, timezone
import io
import logging
import math
from typing import Any, Dict, List, Optional, Set, Tuple
import httpx
import numpy as np
import pandas as pd

from core.cache import cached_or_fetch
from core.config import get_settings
from core.errors import FeedError
from core.geo import haversine_m
from core.models import AOI, FireDetection, ProvenanceRecord

logger = logging.getLogger(__name__)

FIRMS_BASE_URL = "https://firms.modaps.eosdis.nasa.gov/api/area/csv"
VALID_VIIRS_CONFIDENCE = {"n", "h", "nominal", "high"}


def _mask_url(url: str, map_key: str) -> str:
    """Mask the secret map key in URLs for audit provenance and logging."""
    if map_key and map_key in url:
        return url.replace(map_key, "***")
    return url


def parse_firms_csv(csv_text: str, source: str, hours: int, now_utc: Optional[datetime] = None) -> List[FireDetection]:
    """Parse raw FIRMS CSV text into FireDetection objects with strict validation.

    Args:
        csv_text: Raw CSV string response from FIRMS API.
        source: Satellite product identifier (e.g. 'VIIRS_SNPP_NRT', 'MODIS_NRT').
        hours: Maximum age in hours relative to now_utc.
        now_utc: Reference UTC datetime (defaults to datetime.now(timezone.utc)).

    Returns:
        List of validated FireDetection objects.

    Raises:
        FeedError: If CSV text contains an API error message or cannot be parsed.
    """
    clean_text = csv_text.strip()
    if not clean_text:
        return []

    # Check for text or HTML error messages often returned by FIRMS with HTTP 200
    lower_text = clean_text.lower()
    if lower_text.startswith("<!doctype") or "<html" in lower_text:
        raise FeedError("FIRMS API returned HTML error response", source="NASA FIRMS")
    if "invalid map_key" in lower_text or "transaction/time limit" in lower_text:
        raise FeedError(f"FIRMS API authorization error: {clean_text[:120]}", source="NASA FIRMS")
    if lower_text.startswith("error:") or lower_text.startswith("exception:"):
        raise FeedError(f"FIRMS API failure: {clean_text[:120]}", source="NASA FIRMS")

    try:
        df = pd.read_csv(io.StringIO(clean_text))
    except Exception as e:
        raise FeedError(f"Failed to parse FIRMS CSV response: {e}", source="NASA FIRMS")

    if df.empty or "latitude" not in df.columns or "longitude" not in df.columns:
        return []

    if now_utc is None:
        now_utc = datetime.now(timezone.utc)
    cutoff_time = now_utc - timedelta(hours=hours)

    detections: List[FireDetection] = []
    is_viirs = "viirs" in source.lower()
    is_modis = "modis" in source.lower()

    for _, row in df.iterrows():
        try:
            lat = float(row["latitude"])
            lon = float(row["longitude"])
            frp = float(row.get("frp", 0.0))
            raw_conf = str(row.get("confidence", "")).strip().lower()

            # Confidence filtering
            if is_viirs:
                if raw_conf not in VALID_VIIRS_CONFIDENCE:
                    continue
            elif is_modis:
                try:
                    conf_val = float(raw_conf)
                    if conf_val < 30.0:
                        continue
                except ValueError:
                    continue

            # Parse acquisition timestamp (acq_date: YYYY-MM-DD, acq_time: HHMM)
            acq_date_str = str(row["acq_date"]).strip()
            acq_time_raw = str(row["acq_time"]).strip().split(".")[0]
            acq_time_str = acq_time_raw.zfill(4)

            acq_dt = datetime.strptime(
                f"{acq_date_str} {acq_time_str}", "%Y-%m-%d %H%M"
            ).replace(tzinfo=timezone.utc)

            # Filter to detections within the requested hour window
            if acq_dt < cutoff_time:
                continue

            satellite = str(row.get("satellite", source)).strip()
            detections.append(
                FireDetection(
                    lat=lat,
                    lon=lon,
                    acq_time_utc=acq_dt,
                    frp=frp,
                    confidence=raw_conf,
                    satellite=satellite,
                )
            )
        except Exception:
            continue

    return detections


def _fetch_single_source(
    aoi: AOI, hours: int, source: str
) -> Tuple[List[FireDetection], ProvenanceRecord]:
    """Fetch detections from a single FIRMS source."""
    settings = get_settings()

    if settings.SIMULATE_API_FAILURE == "firms":
        raise FeedError("Simulated FIRMS feed failure", source="NASA FIRMS")

    map_key = settings.FIRMS_MAP_KEY.strip()
    if not map_key:
        raise FeedError(
            "FIRMS MAP_KEY is missing or empty. Please set FIRMS_MAP_KEY in .env.",
            source="NASA FIRMS",
        )

    day_range = max(1, min(5, math.ceil(hours / 24.0)))
    raw_url = f"{FIRMS_BASE_URL}/{map_key}/{source}/{aoi.west:.4f},{aoi.south:.4f},{aoi.east:.4f},{aoi.north:.4f}/{day_range}"
    masked_url = _mask_url(raw_url, map_key)
    cache_key = f"firms:{source}:{aoi.west:.4f},{aoi.south:.4f},{aoi.east:.4f},{aoi.north:.4f}:{day_range}"

    def _do_fetch() -> Tuple[bytes, str, str]:
        logger.info("Requesting FIRMS data from %s", masked_url)
        with httpx.Client(timeout=settings.HTTP_TIMEOUT_S) as client:
            resp = client.get(raw_url)
            if resp.status_code != 200:
                raise FeedError(
                    f"HTTP {resp.status_code} from FIRMS: {resp.text[:100]}",
                    source="NASA FIRMS",
                    url=masked_url,
                )
            return resp.content, "NASA FIRMS", masked_url

    content_bytes, prov = cached_or_fetch(
        key=cache_key,
        ttl_s=settings.FIRES_TTL_S,
        fetch_fn=_do_fetch,
        allow_stale=True,
    )

    detections = parse_firms_csv(
        csv_text=content_bytes.decode("utf-8", errors="replace"),
        source=source,
        hours=hours,
    )
    return detections, prov


def deduplicate_detections(detections: List[FireDetection]) -> List[FireDetection]:
    """Deduplicate fire detections within 100m distance and 10 minutes timestamp.

    When duplicate detections occur, the one with the higher Fire Radiative Power (FRP) is kept.
    """
    if len(detections) <= 1:
        return detections

    # Sort descending by FRP so highest intensity detections take precedence
    sorted_dets = sorted(detections, key=lambda d: d.frp, reverse=True)
    kept: List[FireDetection] = []

    for d in sorted_dets:
        is_dup = False
        for k in kept:
            time_diff_s = abs((d.acq_time_utc - k.acq_time_utc).total_seconds())
            if time_diff_s <= 600.0:  # 10 minutes
                dist_m = haversine_m(d.lon, d.lat, k.lon, k.lat)
                if dist_m <= 100.0:
                    is_dup = True
                    break
        if not is_dup:
            kept.append(d)

    return sorted(kept, key=lambda d: d.acq_time_utc)


def fetch_detections(
    aoi: AOI, hours: int = 24, source: str = "VIIRS_SNPP_NRT"
) -> Tuple[List[FireDetection], ProvenanceRecord]:
    """Fetch and merge active fire detections for an AOI from VIIRS_SNPP_NRT and VIIRS_NOAA20_NRT.

    Deduplicates detections occurring within 100m and 10 minutes.

    Args:
        aoi: Area of Interest bounding box.
        hours: Hours of detection history to retrieve (1-120).
        source: Primary satellite source identifier.

    Returns:
        Tuple of (deduplicated_detections, provenance_record).
    """
    primary_dets, prov = _fetch_single_source(aoi, hours, source)

    # Attempt to query second constellation satellite if using VIIRS
    secondary_source = "VIIRS_NOAA20_NRT" if source == "VIIRS_SNPP_NRT" else None
    if secondary_source:
        try:
            sec_dets, _ = _fetch_single_source(aoi, hours, secondary_source)
            primary_dets.extend(sec_dets)
        except Exception as e:
            logger.warning("Could not fetch secondary FIRMS source %s: %s", secondary_source, e)

    deduped = deduplicate_detections(primary_dets)
    return deduped, prov


def find_active_clusters(hours: int = 24, top_n: int = 5) -> List[Dict[str, Any]]:
    """Scan the global FIRMS endpoint and return top active fire clusters.

    Uses a simple 0.25-degree grid binning and merges contiguous bins.

    Args:
        hours: Number of hours to inspect (1-24).
        top_n: Maximum number of candidate clusters to return.

    Returns:
        List of cluster dicts with center_lat, center_lon, count, total_frp, and suggested_aoi.
    """
    settings = get_settings()
    if settings.SIMULATE_API_FAILURE == "firms":
        raise FeedError("Simulated FIRMS feed failure", source="NASA FIRMS")

    map_key = settings.FIRMS_MAP_KEY.strip()
    if not map_key:
        raise FeedError("FIRMS MAP_KEY is not configured", source="NASA FIRMS")

    raw_url = f"{FIRMS_BASE_URL}/{map_key}/VIIRS_SNPP_NRT/world/1"
    masked_url = _mask_url(raw_url, map_key)
    cache_key = "firms:world:1"

    def _do_fetch() -> Tuple[bytes, str, str]:
        logger.info("Requesting global FIRMS data from %s", masked_url)
        with httpx.Client(timeout=settings.HTTP_TIMEOUT_S) as client:
            resp = client.get(raw_url)
            if resp.status_code != 200:
                raise FeedError(
                    f"HTTP {resp.status_code} from global FIRMS: {resp.text[:100]}",
                    source="NASA FIRMS",
                    url=masked_url,
                )
            return resp.content, "NASA FIRMS", masked_url

    content_bytes, _ = cached_or_fetch(
        key=cache_key,
        ttl_s=settings.FIRES_TTL_S,
        fetch_fn=_do_fetch,
        allow_stale=True,
    )

    detections = parse_firms_csv(
        csv_text=content_bytes.decode("utf-8", errors="replace"),
        source="VIIRS_SNPP_NRT",
        hours=hours,
    )

    if not detections:
        return []

    # Bin detections into 0.25-degree grid cells
    bin_size = 0.25
    bins: Dict[Tuple[int, int], List[FireDetection]] = {}

    for d in detections:
        r_bin = int(math.floor(d.lat / bin_size))
        c_bin = int(math.floor(d.lon / bin_size))
        bins.setdefault((r_bin, c_bin), []).append(d)

    # Connected component labeling for adjacent bins (Chebyshev distance <= 1)
    visited: Set[Tuple[int, int]] = set()
    clusters: List[List[FireDetection]] = []

    for b_coord in bins:
        if b_coord in visited:
            continue
        queue = [b_coord]
        visited.add(b_coord)
        cluster_dets: List[FireDetection] = []

        while queue:
            curr = queue.pop(0)
            cluster_dets.extend(bins[curr])
            cr, cc = curr
            for dr in (-1, 0, 1):
                for dc in (-1, 0, 1):
                    neighbor = (cr + dr, cc + dc)
                    if neighbor in bins and neighbor not in visited:
                        visited.add(neighbor)
                        queue.append(neighbor)

        clusters.append(cluster_dets)

    # Compute centroid and statistics for each cluster
    cluster_results: List[Dict[str, Any]] = []
    for c_dets in clusters:
        total_frp = sum(d.frp for d in c_dets)
        count = len(c_dets)

        # FRP-weighted centroid if FRP > 0, else simple mean
        if total_frp > 0:
            center_lat = sum(d.lat * d.frp for d in c_dets) / total_frp
            center_lon = sum(d.lon * d.frp for d in c_dets) / total_frp
        else:
            center_lat = sum(d.lat for d in c_dets) / count
            center_lon = sum(d.lon for d in c_dets) / count

        # Suggested AOI: 0.2 x 0.2 degrees centered at centroid
        suggested_aoi = {
            "west": round(center_lon - 0.1, 4),
            "south": round(center_lat - 0.1, 4),
            "east": round(center_lon + 0.1, 4),
            "north": round(center_lat + 0.1, 4),
        }

        cluster_results.append({
            "center_lat": round(center_lat, 4),
            "center_lon": round(center_lon, 4),
            "count": count,
            "total_frp": round(total_frp, 2),
            "suggested_aoi": suggested_aoi,
        })

    # Sort descending by total FRP and return top_n
    cluster_results.sort(key=lambda c: c["total_frp"], reverse=True)
    return cluster_results[:top_n]

