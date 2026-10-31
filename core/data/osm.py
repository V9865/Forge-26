"""OpenStreetMap road graph, settlement, and shelter data provider for EmberRoute.

Provides functions to download and process:
1. Drivable road networks as NetworkX MultiDiGraphs with edge speeds and travel times.
2. Population settlements snapped to graph nodes with spatial deduplication.
3. Designated shelter locations (schools, hospitals, community centres).

Coordinate conventions:
- Unprojected WGS84: (lon, lat) order for Shapely geometries and bounding boxes (west, south, east, north).
- Explicit (lat, lon) attributes on Settlement data models.
- Speeds are in km/h; lengths are in metres; travel times are in seconds.
"""

from datetime import datetime, timezone
import hashlib
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import warnings

import networkx as nx
import numpy as np
import osmnx as ox

from core.config import get_settings
from core.errors import FeedError, StaleCacheWarning
from core.geo import haversine_m
from core.models import AOI, ProvenanceRecord, Settlement

logger = logging.getLogger(__name__)

# Overpass API endpoints
PRIMARY_OVERPASS_URL = "https://overpass-api.de/api"
ALT_OVERPASS_URL = "https://overpass.kumi.systems/api"
MIRROR_OVERPASS_URL = "https://overpass.osm.ch/api"

# Cache TTL: 30 days in seconds
OSM_CACHE_TTL_S = 30 * 24 * 3600

# Conservative highway speed defaults in km/h
DEFAULT_HWY_SPEEDS: Dict[str, float] = {
    "residential": 25.0,
    "tertiary": 35.0,
    "secondary": 45.0,
    "primary": 55.0,
    "trunk": 60.0,
    "unclassified": 30.0,
    "track": 15.0,
    "service": 15.0,
}
FALLBACK_SPEED_KPH = 30.0

# Hierarchy for ranking settlement place importance (lower value = higher priority)
PLACE_RANKINGS: Dict[str, int] = {
    "city": 1,
    "town": 2,
    "suburb": 3,
    "village": 4,
    "hamlet": 5,
    "locality": 6,
}


def _get_osm_cache_dir() -> Path:
    """Return the OSM cache directory under CACHE_DIR, creating it if needed."""
    cache_dir = Path(get_settings().CACHE_DIR) / "osm"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def _cache_key_for_aoi(aoi: AOI) -> str:
    """Generate a stable cache key string from AOI bounding box coordinates."""
    return f"osm_graph_{aoi.west:.5f}_{aoi.south:.5f}_{aoi.east:.5f}_{aoi.north:.5f}"


def _hash_key(key: str) -> str:
    """Hash cache key to a hexadecimal string."""
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def _format_bbox_for_osmnx(aoi: AOI) -> Tuple[float, float, float, float]:
    """Format AOI as OSMnx 2.x bbox tuple: (left, bottom, right, top) = (west, south, east, north)."""
    return (float(aoi.west), float(aoi.south), float(aoi.east), float(aoi.north))


def get_road_graph(aoi: AOI) -> nx.MultiDiGraph:
    """Retrieve drivable road network graph for an AOI.

    Queries OpenStreetMap via OSMnx within the AOI bounding box, retains the
    largest strongly connected component, assigns conservative speeds, and
    calculates edge travel times. Results are cached to disk as GraphML (TTL 30 days).

    Retries on an alternate Overpass endpoint before failing.
    Honours SIMULATE_API_FAILURE=overpass by raising FeedError at download step only.

    Args:
        aoi: Area of Interest bounding box (west, south, east, north).

    Returns:
        nx.MultiDiGraph: Drivable road network graph with 'speed_kph' and 'travel_time'
                         attributes on edges.

    Raises:
        FeedError: If all Overpass endpoints fail or simulated failure is active.
    """
    settings = get_settings()
    key = _cache_key_for_aoi(aoi)
    h = _hash_key(key)
    cache_dir = _get_osm_cache_dir()
    graphml_path = cache_dir / f"{h}.graphml"
    meta_path = cache_dir / f"{h}.json"

    # 1. Check disk cache
    stale_graph: Optional[nx.MultiDiGraph] = None
    if graphml_path.exists() and meta_path.exists():
        try:
            meta_dict = json.loads(meta_path.read_text(encoding="utf-8"))
            fetched_at = datetime.fromisoformat(meta_dict["fetched_at_utc"])
            now_utc = datetime.now(timezone.utc)
            age_s = (now_utc - fetched_at).total_seconds()
            loaded_g = ox.io.load_graphml(graphml_path)

            if age_s <= OSM_CACHE_TTL_S:
                logger.info("Loaded road graph for AOI from fresh cache (%s, age %.1f hours)", h[:8], age_s / 3600.0)
                return loaded_g
            else:
                logger.warning("OSM cache for AOI is expired (age %.1f days)", age_s / 86400.0)
                stale_graph = loaded_g
        except Exception as exc:
            logger.warning("Failed reading cached road graph %s: %s", graphml_path, exc)

    # 2. Check for simulated failure before making network calls
    sim_failure = getattr(settings, "SIMULATE_API_FAILURE", "") or os.environ.get("SIMULATE_API_FAILURE", "")
    if sim_failure == "overpass":
        logger.info("SIMULATE_API_FAILURE=overpass triggered")
        raise FeedError(
            message="Simulated Overpass API failure",
            source="OpenStreetMap",
            url=f"{PRIMARY_OVERPASS_URL}/interpreter",
        )

    # 3. Configure OSMnx settings and attempt download with retry
    bbox = _format_bbox_for_osmnx(aoi)
    orig_endpoint = ox.settings.overpass_url
    orig_timeout = ox.settings.requests_timeout
    ox.settings.requests_timeout = settings.HTTP_TIMEOUT_S

    endpoints_to_try = [
        PRIMARY_OVERPASS_URL,
        ALT_OVERPASS_URL,
        MIRROR_OVERPASS_URL,
    ]
    orig_rate_limit = ox.settings.overpass_rate_limit
    ox.settings.overpass_rate_limit = False

    downloaded_g: Optional[nx.MultiDiGraph] = None
    last_error: Optional[Exception] = None
    endpoint_used = PRIMARY_OVERPASS_URL

    try:
        for idx, endpoint in enumerate(endpoints_to_try):
            ox.settings.overpass_url = endpoint
            endpoint_used = endpoint
            try:
                logger.info("Querying Overpass (%s) for drivable roads in bbox %s", endpoint, bbox)
                downloaded_g = ox.graph_from_bbox(
                    bbox=bbox,
                    network_type="drive",
                    simplify=True,
                    retain_all=False,
                )
                if downloaded_g is not None and len(downloaded_g) > 0:
                    break
            except Exception as exc:
                last_error = exc
                logger.warning("Overpass query to %s failed: %s", endpoint, exc)
                if idx < len(endpoints_to_try) - 1:
                    logger.info("Retrying with alternate Overpass endpoint...")
    finally:
        ox.settings.overpass_url = orig_endpoint
        ox.settings.requests_timeout = orig_timeout
        ox.settings.overpass_rate_limit = orig_rate_limit

    if downloaded_g is None or len(downloaded_g) == 0:
        if stale_graph is not None:
            warnings.warn(
                f"Overpass network request failed ({last_error}). Falling back to stale cached road graph.",
                category=StaleCacheWarning,
                stacklevel=2,
            )
            logger.warning("Falling back to stale road graph from cache.")
            return stale_graph

        raise FeedError(
            message=f"Failed to download road network from all Overpass endpoints: {last_error}",
            source="OpenStreetMap",
            url=f"{endpoint_used}/interpreter",
        )

    # 4. Retain largest strongly connected component
    if len(downloaded_g) > 0:
        downloaded_g = ox.truncate.largest_component(downloaded_g, strongly=True)

    # 5. Add speeds and travel times
    downloaded_g = ox.routing.add_edge_speeds(
        downloaded_g,
        hwy_speeds=DEFAULT_HWY_SPEEDS,
        fallback=FALLBACK_SPEED_KPH,
    )
    downloaded_g = ox.routing.add_edge_travel_times(downloaded_g)

    # 6. Save to disk cache
    try:
        ox.io.save_graphml(downloaded_g, filepath=graphml_path)
        now_utc = datetime.now(timezone.utc)
        meta_dict = {
            "name": key,
            "source": "OpenStreetMap",
            "url": f"{endpoint_used}/interpreter",
            "fetched_at_utc": now_utc.isoformat(),
            "ttl_s": OSM_CACHE_TTL_S,
            "is_stale": False,
            "nodes_count": len(downloaded_g.nodes),
            "edges_count": len(downloaded_g.edges),
        }
        meta_path.write_text(json.dumps(meta_dict, indent=2), encoding="utf-8")
        logger.info("Saved road graph to cache: %s (%d nodes, %d edges)", graphml_path, len(downloaded_g.nodes), len(downloaded_g.edges))
    except Exception as exc:
        logger.warning("Failed writing road graph cache %s: %s", graphml_path, exc)

    return downloaded_g


def get_settlements(aoi: AOI, G: nx.MultiDiGraph) -> List[Settlement]:
    """Retrieve named populated settlements in an AOI and snap to road graph nodes.

    Queries OpenStreetMap for place tags: village, hamlet, town, suburb, locality.
    Filters unnamed places, sorts by place size hierarchy, snaps each to the
    nearest graph node, and de-duplicates settlements snapping to the same node
    within 300 metres of an already chosen settlement. Capped at 60 settlements.

    Args:
        aoi: Area of Interest bounding box.
        G: Drivable road network graph.

    Returns:
        List[Settlement]: Up to 60 snapped and deduplicated settlements.
    """
    settings = get_settings()
    sim_failure = getattr(settings, "SIMULATE_API_FAILURE", "") or os.environ.get("SIMULATE_API_FAILURE", "")
    if sim_failure == "overpass":
        raise FeedError(
            message="Simulated Overpass API failure",
            source="OpenStreetMap",
            url=f"{PRIMARY_OVERPASS_URL}/interpreter",
        )

    # 1. Check disk cache for settlements
    cache_dir = _get_osm_cache_dir()
    h = _hash_key(_cache_key_for_aoi(aoi))
    settlements_path = cache_dir / f"{h}_settlements.json"

    if settlements_path.exists():
        try:
            cached_data = json.loads(settlements_path.read_text(encoding="utf-8"))
            fetched_at = datetime.fromisoformat(cached_data["fetched_at_utc"])
            age_s = (datetime.now(timezone.utc) - fetched_at).total_seconds()
            loaded_s = [Settlement(**s) for s in cached_data.get("settlements", [])]
            if age_s <= OSM_CACHE_TTL_S:
                logger.info("Loaded settlements for AOI from fresh cache (%s, count %d)", h[:8], len(loaded_s))
                return loaded_s
        except Exception as exc:
            logger.warning("Failed reading cached settlements %s: %s", settlements_path, exc)

    bbox = _format_bbox_for_osmnx(aoi)
    tags: Dict[str, Any] = {"place": ["village", "hamlet", "town", "suburb", "locality"]}

    orig_endpoint = ox.settings.overpass_url
    orig_timeout = ox.settings.requests_timeout
    ox.settings.requests_timeout = settings.HTTP_TIMEOUT_S

    endpoints_to_try = [
        PRIMARY_OVERPASS_URL,
        ALT_OVERPASS_URL,
        MIRROR_OVERPASS_URL,
    ]
    orig_rate_limit = ox.settings.overpass_rate_limit
    ox.settings.overpass_rate_limit = False

    gdf = None
    last_error: Optional[Exception] = None
    try:
        for idx, endpoint in enumerate(endpoints_to_try):
            ox.settings.overpass_url = endpoint
            try:
                gdf = ox.features_from_bbox(bbox=bbox, tags=tags)
                break
            except Exception as exc:
                last_error = exc
                logger.warning("Overpass features_from_bbox failed on %s: %s", endpoint, exc)
                if idx < len(endpoints_to_try) - 1:
                    logger.info("Retrying with alternate Overpass endpoint for settlements...")
    finally:
        ox.settings.overpass_url = orig_endpoint
        ox.settings.requests_timeout = orig_timeout
        ox.settings.overpass_rate_limit = orig_rate_limit

    if gdf is None or len(gdf) == 0:
        logger.info("No settlement features found for AOI")
        return []

    # Filter unnamed features
    if "name" not in gdf.columns:
        return []
    valid_mask = gdf["name"].notna() & (gdf["name"].astype(str).str.strip() != "")
    gdf = gdf[valid_mask]
    if len(gdf) == 0:
        return []

    # Extract coordinates (Point or Centroid) and place type
    candidates: List[Dict[str, Any]] = []
    for idx, row in gdf.iterrows():
        geom = row.geometry
        if geom is None:
            continue

        if geom.geom_type == "Point":
            lat = float(geom.y)
            lon = float(geom.x)
        else:
            centroid = geom.centroid
            lat = float(centroid.y)
            lon = float(centroid.x)

        place_val = str(row.get("place", "locality")).lower()
        rank = PLACE_RANKINGS.get(place_val, 99)

        # OSM ID extraction
        osmid_val = row.get("osmid")
        if osmid_val is None or (isinstance(osmid_val, float) and np.isnan(osmid_val)):
            osmid_str = str(idx)
        else:
            osmid_str = str(osmid_val)

        candidates.append({
            "id": osmid_str,
            "name": str(row["name"]).strip(),
            "lat": lat,
            "lon": lon,
            "place": place_val,
            "rank": rank,
        })

    # Sort so biggest place types come first (lower rank number = higher importance)
    candidates.sort(key=lambda c: c["rank"])

    # Snap to graph nodes and deduplicate within 300 m
    has_graph_nodes = len(G.nodes) > 0
    settlements: List[Settlement] = []
    # Map node_id -> list of accepted settlements snapped to it
    snapped_by_node: Dict[int, List[Settlement]] = {}

    for cand in candidates:
        if has_graph_nodes:
            snapped_node_id = int(ox.distance.nearest_nodes(G, X=cand["lon"], Y=cand["lat"]))
        else:
            snapped_node_id = None

        # Check duplicate snapping: drop if another settlement on the same node is <= 300 m
        if snapped_node_id is not None and snapped_node_id in snapped_by_node:
            is_duplicate = False
            for prev in snapped_by_node[snapped_node_id]:
                dist_m = haversine_m(cand["lon"], cand["lat"], prev.lon, prev.lat)
                if dist_m <= 300.0:
                    is_duplicate = True
                    break
            if is_duplicate:
                continue

        st = Settlement(
            id=cand["id"],
            name=cand["name"],
            lat=cand["lat"],
            lon=cand["lon"],
            node=snapped_node_id,
        )
        settlements.append(st)
        if snapped_node_id is not None:
            snapped_by_node.setdefault(snapped_node_id, []).append(st)

        if len(settlements) >= 60:
            break

    logger.info("Extracted and snapped %d settlements for AOI", len(settlements))
    try:
        cache_data = {
            "fetched_at_utc": datetime.now(timezone.utc).isoformat(),
            "settlements": [s.model_dump() for s in settlements],
        }
        settlements_path.write_text(json.dumps(cache_data), encoding="utf-8")
    except Exception as exc:
        logger.warning("Failed saving settlements cache: %s", exc)
    return settlements


def get_shelters(aoi: AOI) -> List[Tuple[str, float, float, str]]:
    """Retrieve designated emergency shelters within an AOI.

    Queries OpenStreetMap for amenity tags in {school, hospital, community_centre}.

    Args:
        aoi: Area of Interest bounding box.

    Returns:
        List of tuples: (name, lat, lon, kind)
    """
    settings = get_settings()
    sim_failure = getattr(settings, "SIMULATE_API_FAILURE", "") or os.environ.get("SIMULATE_API_FAILURE", "")
    if sim_failure == "overpass":
        raise FeedError(
            message="Simulated Overpass API failure",
            source="OpenStreetMap",
            url=f"{PRIMARY_OVERPASS_URL}/interpreter",
        )

    # 1. Check disk cache for shelters
    cache_dir = _get_osm_cache_dir()
    h = _hash_key(_cache_key_for_aoi(aoi))
    shelters_path = cache_dir / f"{h}_shelters.json"

    if shelters_path.exists():
        try:
            cached_data = json.loads(shelters_path.read_text(encoding="utf-8"))
            fetched_at = datetime.fromisoformat(cached_data["fetched_at_utc"])
            age_s = (datetime.now(timezone.utc) - fetched_at).total_seconds()
            loaded_sh = [tuple(item) for item in cached_data.get("shelters", [])]
            if age_s <= OSM_CACHE_TTL_S:
                logger.info("Loaded shelters for AOI from fresh cache (%s, count %d)", h[:8], len(loaded_sh))
                return loaded_sh
        except Exception as exc:
            logger.warning("Failed reading cached shelters %s: %s", shelters_path, exc)

    bbox = _format_bbox_for_osmnx(aoi)
    tags: Dict[str, Any] = {"amenity": ["school", "hospital", "community_centre"]}

    orig_endpoint = ox.settings.overpass_url
    orig_timeout = ox.settings.requests_timeout
    ox.settings.requests_timeout = settings.HTTP_TIMEOUT_S

    endpoints_to_try = [
        PRIMARY_OVERPASS_URL,
        ALT_OVERPASS_URL,
        MIRROR_OVERPASS_URL,
    ]
    orig_rate_limit = ox.settings.overpass_rate_limit
    ox.settings.overpass_rate_limit = False

    gdf = None
    try:
        for idx, endpoint in enumerate(endpoints_to_try):
            ox.settings.overpass_url = endpoint
            try:
                gdf = ox.features_from_bbox(bbox=bbox, tags=tags)
                break
            except Exception as exc:
                logger.warning("Overpass features_from_bbox for shelters failed on %s: %s", endpoint, exc)
                if idx < len(endpoints_to_try) - 1:
                    logger.info("Retrying with alternate Overpass endpoint for shelters...")
    finally:
        ox.settings.overpass_url = orig_endpoint
        ox.settings.requests_timeout = orig_timeout
        ox.settings.overpass_rate_limit = orig_rate_limit

    if gdf is None or len(gdf) == 0:
        logger.info("No shelter features found for AOI")
        return []

    shelters: List[Tuple[str, float, float, str]] = []
    for idx, row in gdf.iterrows():
        geom = row.geometry
        if geom is None:
            continue

        if geom.geom_type == "Point":
            lat = float(geom.y)
            lon = float(geom.x)
        else:
            centroid = geom.centroid
            lat = float(centroid.y)
            lon = float(centroid.x)

        kind = str(row.get("amenity", "shelter")).strip()
        raw_name = row.get("name")
        if raw_name is not None and not (isinstance(raw_name, float) and np.isnan(raw_name)) and str(raw_name).strip():
            name = str(raw_name).strip()
        else:
            kind_label = kind.replace("_", " ").title()
            name = f"{kind_label} ({lat:.3f}, {lon:.3f})"

        shelters.append((name, lat, lon, kind))

    logger.info("Extracted %d shelters for AOI", len(shelters))
    try:
        cache_data = {
            "fetched_at_utc": datetime.now(timezone.utc).isoformat(),
            "shelters": shelters,
        }
        shelters_path.write_text(json.dumps(cache_data), encoding="utf-8")
    except Exception as exc:
        logger.warning("Failed saving shelters cache: %s", exc)
    return shelters

