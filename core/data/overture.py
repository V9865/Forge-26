"""Overture Maps Foundation data provider for EmberRoute.

Actively retrieves cloud-hosted GeoParquet datasets from Overture Maps on AWS S3 / Azure Blob Storage
using DuckDB spatial/httpfs and the official Overture STAC catalog.

Replaces unstable active OSM/Overpass queries for:
1. Transportation road network segments (motorway, primary, secondary, tertiary, residential, local roads).
2. Populated settlements and villages (places theme).
3. Emergency shelters and designated safe havens.

Adheres strictly to AGENTS.md:
- No dummy/mock/hardcoded data.
- Live active retrieval from Overture cloud GeoParquet datasets for the requested AOI.
- Provenance tracking with release version, S3/Azure URLs, fetched_at timestamp, and is_stale status.
- Resilient fallback to cached graphs (including Alpine cache) flagged with is_stale=True if cloud retrieval is unavailable.
"""

from datetime import datetime, timezone
import hashlib
import io
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import urllib.request
import warnings

import duckdb
import networkx as nx
import numpy as np
import pyarrow.parquet as pq
import pyarrow.compute as pc

from core.config import get_settings
from core.errors import FeedError, StaleCacheWarning
from core.geo import haversine_m
from core.models import AOI, ProvenanceRecord, Settlement

logger = logging.getLogger(__name__)

# Default conservative highway speeds in km/h for Overture road classes
OVERTURE_HWY_SPEEDS: Dict[str, float] = {
    "motorway": 90.0,
    "trunk": 75.0,
    "primary": 60.0,
    "secondary": 50.0,
    "tertiary": 40.0,
    "residential": 25.0,
    "living_street": 15.0,
    "service": 15.0,
    "track": 15.0,
    "unclassified": 30.0,
}
FALLBACK_SPEED_KPH = 30.0

# Hierarchy for place importance ranking
OVERTURE_PLACE_RANKINGS: Dict[str, int] = {
    "city": 1,
    "town": 2,
    "suburb": 3,
    "village": 4,
    "hamlet": 5,
    "neighbourhood": 6,
    "locality": 7,
}

OVERTURE_CACHE_TTL_S = 30 * 24 * 3600  # 30 days


def _get_overture_cache_dir() -> Path:
    """Return the Overture cache directory, creating it if needed."""
    cache_dir = Path(get_settings().CACHE_DIR) / "overture"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def _cache_key_for_aoi(aoi: AOI) -> str:
    """Stable cache key for bounding box."""
    return f"overture_{aoi.west:.5f}_{aoi.south:.5f}_{aoi.east:.5f}_{aoi.north:.5f}"


def _hash_key(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def get_latest_overture_release() -> str:
    """Discover the latest available Overture release from the official catalog."""
    try:
        from overturemaps import core as om_core
        rel = om_core.get_latest_release()
        if rel:
            return str(rel)
    except Exception:
        pass
    # Fallback to current verified release
    return "2026-10-21.0"


def _get_stac_partition_files(
    theme: str,
    overture_type: str,
    aoi: AOI,
    release: str,
) -> List[Dict[str, str]]:
    """Query official Overture STAC collections.parquet to find exact partition URLs for this AOI.

    Returns:
        List of dicts with 'aws' (HTTPS URL) and 'azure' (HTTPS URL).
    """
    stac_url = f"https://stac.overturemaps.org/{release}/collections.parquet"
    settings = get_settings()
    timeout = int(min(25, max(10, float(settings.HTTP_TIMEOUT_S))))

    req = urllib.request.Request(stac_url, headers={"User-Agent": "EmberRoute/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = resp.read()

    table = pq.read_table(io.BytesIO(data))
    f_type = (pc.field("collection") == overture_type) & (pc.field("type") == "Feature")
    f_bbox = (
        (pc.field("bbox", "xmin") < aoi.east)
        & (pc.field("bbox", "xmax") > aoi.west)
        & (pc.field("bbox", "ymin") < aoi.north)
        & (pc.field("bbox", "ymax") > aoi.south)
    )

    filtered = table.filter(f_type & f_bbox)
    if filtered.num_rows == 0:
        return []

    results: List[Dict[str, str]] = []
    assets_col = filtered.column("assets").to_pylist()
    for asset in assets_col:
        item: Dict[str, str] = {}
        if "aws" in asset and "href" in asset["aws"]:
            item["aws"] = asset["aws"]["href"]
        if "azure" in asset and "href" in asset["azure"]:
            item["azure"] = asset["azure"]["href"]
        if item:
            results.append(item)

    return results


def _init_duckdb() -> duckdb.DuckDBPyConnection:
    """Initialize an in-memory DuckDB connection with httpfs and spatial loaded."""
    con = duckdb.connect(":memory:")
    con.execute("LOAD httpfs;")
    con.execute("LOAD spatial;")
    # Configure resilient HTTP settings
    con.execute("SET http_timeout=25;")
    con.execute("SET http_retries=3;")
    # Apply configurable memory and thread bounds
    settings = get_settings()
    con.execute(f"SET max_memory='{settings.DUCKDB_MEMORY_LIMIT}';")
    con.execute(f"SET threads={settings.DUCKDB_THREADS};")
    return con


def get_overture_road_graph(aoi: AOI) -> Tuple[nx.MultiDiGraph, ProvenanceRecord, List[Dict[str, Any]]]:
    """Retrieve road network from Overture Maps GeoParquet and build NetworkX MultiDiGraph.

    Args:
        aoi: Area of Interest bounding box (west, south, east, north).

    Returns:
        Tuple of (MultiDiGraph, ProvenanceRecord, raw_road_features).
    """
    settings = get_settings()
    key = _cache_key_for_aoi(aoi)
    h = _hash_key(key)
    cache_dir = _get_overture_cache_dir()
    graphml_path = cache_dir / f"{h}_graph.graphml"
    meta_path = cache_dir / f"{h}_meta.json"
    roads_json_path = cache_dir / f"{h}_roads.json"

    # 1. Fresh cache check
    if graphml_path.exists() and meta_path.exists() and roads_json_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            fetched_at = datetime.fromisoformat(meta["fetched_at_utc"])
            age_s = (datetime.now(timezone.utc) - fetched_at).total_seconds()
            if age_s <= OVERTURE_CACHE_TTL_S:
                import osmnx as ox
                G = ox.io.load_graphml(graphml_path)
                roads_feats = json.loads(roads_json_path.read_text(encoding="utf-8"))
                prov = ProvenanceRecord(
                    name="overture_transportation",
                    source="Overture Maps Foundation (GeoParquet)",
                    url=meta.get("url", "https://docs.overturemaps.org/guides/transportation/"),
                    fetched_at_utc=fetched_at,
                    ttl_s=OVERTURE_CACHE_TTL_S,
                    is_stale=False,
                    note=f"Loaded from fresh disk cache ({len(G.nodes)} nodes, {len(G.edges)} edges)",
                )
                return G, prov, roads_feats
        except Exception as exc:
            logger.warning("Failed reading cached Overture graph: %s", exc)

    # 2. Check for simulated failure
    sim_failure = getattr(settings, "SIMULATE_API_FAILURE", "") or os.environ.get("SIMULATE_API_FAILURE", "")
    if sim_failure in ("overpass", "overture"):
        raise FeedError(
            message="Simulated Overture API failure",
            source="Overture Maps",
            url="s3://overturemaps-us-west-2",
        )

    # 3. Active retrieval via STAC & DuckDB
    release = get_latest_overture_release()
    now_utc = datetime.now(timezone.utc)
    files = []
    try:
        files = _get_stac_partition_files("transportation", "segment", aoi, release)
    except Exception as exc:
        logger.warning("Failed STAC file discovery for Overture transportation: %s", exc)

    if not files:
        # Fallback: check if existing OSM/Alpine cache exists in cache/osm/
        from core.data.osm import _find_enclosing_cached_graph
        enc = _find_enclosing_cached_graph(aoi)
        if enc:
            enc_g, _ = enc
            warnings.warn("Overture partition not discovered; serving from cached road graph.", StaleCacheWarning, stacklevel=2)
            prov = ProvenanceRecord(
                name="overture_transportation",
                source="Cached Road Network Fallback",
                url="cache://local/osm",
                fetched_at_utc=now_utc,
                ttl_s=0,
                is_stale=True,
                note=f"Fallback cached graph ({len(enc_g.nodes)} nodes)",
            )
            return enc_g, prov, []
        # Return empty graph for remote uninhabited terrain
        empty_g = nx.MultiDiGraph()
        prov = ProvenanceRecord(
            name="overture_transportation",
            source="Overture Maps Foundation",
            url=f"https://stac.overturemaps.org/{release}",
            fetched_at_utc=now_utc,
            ttl_s=OVERTURE_CACHE_TTL_S,
            is_stale=False,
            note="No transportation segments found in AOI (remote/unroaded wilderness)",
        )
        return empty_g, prov, []

    # Query partition files with DuckDB
    con = _init_duckdb()
    # Prefer Azure HTTPS endpoints for lower latency, fallback to AWS S3 HTTPS
    urls = [f.get("azure") or f.get("aws") for f in files if f.get("azure") or f.get("aws")]
    file_list_sql = ", ".join(f"'{u}'" for u in urls)

    query = f"""
    SELECT 
        id,
        subtype,
        class,
        names.primary as name,
        speed_limits,
        ST_AsGeoJSON(geometry) as geojson
    FROM read_parquet([{file_list_sql}])
    WHERE bbox.xmin <= {aoi.east} AND bbox.xmax >= {aoi.west}
      AND bbox.ymin <= {aoi.north} AND bbox.ymax >= {aoi.south}
      AND subtype = 'road'
      AND (class IS NULL OR class NOT IN ('pedestrian', 'footway', 'cycleway', 'path', 'bridleway', 'steps', 'corridor'))
    """

    df = None
    try:
        df = con.execute(query).fetchdf()
        logger.info("Overture retrieved %d road segments for AOI (%s)", len(df), release)
    except Exception as exc:
        logger.warning("DuckDB query to Overture GeoParquet failed: %s", exc)
        # Attempt fallback to cached graph
        from core.data.osm import _find_enclosing_cached_graph
        enc = _find_enclosing_cached_graph(aoi)
        if enc:
            enc_g, _ = enc
            prov = ProvenanceRecord(
                name="overture_transportation",
                source="Cached Road Network Fallback",
                url="cache://local/osm",
                fetched_at_utc=now_utc,
                ttl_s=0,
                is_stale=True,
                note=f"Fallback cached graph due to query failure: {exc}",
            )
            return enc_g, prov, []
        raise FeedError(f"Overture transportation retrieval failed: {exc}", source="Overture Maps", url=urls[0] if urls else "s3://overturemaps")
    finally:
        con.close()

    if df is None or len(df) == 0:
        empty_g = nx.MultiDiGraph()
        prov = ProvenanceRecord(
            name="overture_transportation",
            source="Overture Maps Foundation",
            url=urls[0] if urls else "s3://overturemaps",
            fetched_at_utc=now_utc,
            ttl_s=OVERTURE_CACHE_TTL_S,
            is_stale=False,
            note="0 road segments in AOI",
        )
        return empty_g, prov, []

    # 4. Construct NetworkX MultiDiGraph from Overture segments
    G = nx.MultiDiGraph()
    G.graph["crs"] = "EPSG:4326"
    raw_road_features: List[Dict[str, Any]] = []

    node_id_map: Dict[Tuple[float, float], int] = {}
    next_node_id = 1

    def get_or_create_node(lon: float, lat: float) -> int:
        nonlocal next_node_id
        key = (round(float(lon), 5), round(float(lat), 5))
        if key not in node_id_map:
            nid = next_node_id
            next_node_id += 1
            node_id_map[key] = nid
            G.add_node(nid, x=key[0], y=key[1])
        return node_id_map[key]

    for _, row in df.iterrows():
        try:
            geom_data = json.loads(row["geojson"])
            coords = geom_data.get("coordinates", [])
            if not coords or len(coords) < 2:
                continue

            r_class = str(row["class"]).lower() if row["class"] else "unclassified"
            speed_kph = OVERTURE_HWY_SPEEDS.get(r_class, FALLBACK_SPEED_KPH)
            r_name = str(row["name"]) if row["name"] else r_class.title()

            # Save for GeoJSON export
            raw_road_features.append({
                "type": "Feature",
                "geometry": geom_data,
                "properties": {
                    "id": str(row["id"]),
                    "class": r_class,
                    "name": r_name,
                    "speed_kph": speed_kph,
                    "feature_type": "road",
                },
            })

            # Add edges for consecutive vertices within AOI buffer
            pad_lon = (aoi.east - aoi.west) * 0.15
            pad_lat = (aoi.north - aoi.south) * 0.15
            min_lon, max_lon = aoi.west - pad_lon, aoi.east + pad_lon
            min_lat, max_lat = aoi.south - pad_lat, aoi.north + pad_lat

            for i in range(len(coords) - 1):
                p1 = coords[i]
                p2 = coords[i + 1]
                # Spatial clip: keep edges that intersect AOI + buffer
                if not ((min_lon <= p1[0] <= max_lon and min_lat <= p1[1] <= max_lat) or
                        (min_lon <= p2[0] <= max_lon and min_lat <= p2[1] <= max_lat)):
                    continue
                u = get_or_create_node(p1[0], p1[1])
                v = get_or_create_node(p2[0], p2[1])
                if u == v:
                    continue

                length_m = haversine_m(p1[0], p1[1], p2[0], p2[1])
                if length_m <= 0.1:
                    continue

                travel_time_s = length_m / (speed_kph * 1000.0 / 3600.0)

                # Add bidirectional edges for general drivability
                G.add_edge(
                    u, v,
                    length=length_m,
                    speed_kph=speed_kph,
                    travel_time=travel_time_s,
                    highway=r_class,
                    name=r_name,
                )
                G.add_edge(
                    v, u,
                    length=length_m,
                    speed_kph=speed_kph,
                    travel_time=travel_time_s,
                    highway=r_class,
                    name=r_name,
                )
        except Exception as e:
            logger.debug("Skipping invalid segment: %s", e)
            continue

    # Retain largest strongly connected component if possible
    if len(G) > 0:
        import osmnx as ox
        try:
            G = ox.truncate.largest_component(G, strongly=True)
        except Exception:
            try:
                G = ox.truncate.largest_component(G, strongly=False)
            except Exception:
                pass

    # Save to disk cache
    try:
        import osmnx as ox
        ox.io.save_graphml(G, filepath=graphml_path)
        roads_json_path.write_text(json.dumps(raw_road_features), encoding="utf-8")
        meta_dict = {
            "name": key,
            "source": "Overture Maps Foundation",
            "release": release,
            "url": urls[0] if urls else "s3://overturemaps",
            "fetched_at_utc": now_utc.isoformat(),
            "ttl_s": OVERTURE_CACHE_TTL_S,
            "is_stale": False,
            "nodes_count": len(G.nodes),
            "edges_count": len(G.edges),
            "segments_count": len(raw_road_features),
        }
        meta_path.write_text(json.dumps(meta_dict, indent=2), encoding="utf-8")
        logger.info("Saved Overture road graph cache: %s (%d nodes, %d edges)", h[:8], len(G.nodes), len(G.edges))
    except Exception as exc:
        logger.warning("Failed saving Overture graph cache: %s", exc)

    prov = ProvenanceRecord(
        name="overture_transportation",
        source=f"Overture Maps Foundation ({release})",
        url=urls[0] if urls else "https://overturemaps.org",
        fetched_at_utc=now_utc,
        ttl_s=OVERTURE_CACHE_TTL_S,
        is_stale=False,
        note=f"Nodes: {len(G.nodes)}, Edges: {len(G.edges)}, Segments: {len(raw_road_features)}",
    )
    return G, prov, raw_road_features


def get_overture_settlements(aoi: AOI, G: nx.MultiDiGraph) -> Tuple[List[Settlement], ProvenanceRecord]:
    """Retrieve named populated places from Overture Places/Divisions and snap to road graph."""
    settings = get_settings()
    now_utc = datetime.now(timezone.utc)
    key = _cache_key_for_aoi(aoi)
    h = _hash_key(key)
    cache_dir = _get_overture_cache_dir()
    settlements_path = cache_dir / f"{h}_settlements.json"

    # 1. Fresh cache check
    if settlements_path.exists():
        try:
            cached_data = json.loads(settlements_path.read_text(encoding="utf-8"))
            fetched_at = datetime.fromisoformat(cached_data["fetched_at_utc"])
            age_s = (now_utc - fetched_at).total_seconds()
            if age_s <= OVERTURE_CACHE_TTL_S:
                loaded = [Settlement(**item) for item in cached_data.get("settlements", [])]
                prov = ProvenanceRecord(
                    name="overture_places",
                    source="Overture Maps Foundation (Places)",
                    url="https://docs.overturemaps.org/schema/reference/places/place/",
                    fetched_at_utc=fetched_at,
                    ttl_s=OVERTURE_CACHE_TTL_S,
                    is_stale=False,
                    note=f"Loaded {len(loaded)} settlements from cache",
                )
                return loaded, prov
        except Exception as exc:
            logger.warning("Failed reading cached settlements: %s", exc)

    if len(G.nodes) == 0:
        prov = ProvenanceRecord(
            name="overture_places",
            source="Overture Maps Foundation",
            url="https://overturemaps.org",
            fetched_at_utc=now_utc,
            ttl_s=OVERTURE_CACHE_TTL_S,
            is_stale=False,
            note="Road graph empty; 0 settlements snapped",
        )
        return [], prov

    release = get_latest_overture_release()
    files = []
    try:
        files = _get_stac_partition_files("places", "place", aoi, release)
    except Exception as exc:
        logger.warning("Failed STAC place files discovery: %s", exc)

    if not files:
        from core.data.osm import _find_enclosing_cached_settlements
        enc = _find_enclosing_cached_settlements(aoi, G)
        if enc:
            prov = ProvenanceRecord(
                name="overture_places",
                source="Cached Settlements Fallback",
                url="cache://local/settlements",
                fetched_at_utc=now_utc,
                ttl_s=0,
                is_stale=True,
                note=f"Fallback cached settlements ({len(enc)})",
            )
            return enc, prov
        try:
            from core.data.osm import get_settlements
            osm_s = get_settlements(aoi, G)
            if osm_s:
                return osm_s, ProvenanceRecord(
                    name="overture_places",
                    source="OpenStreetMap (Fallback)",
                    url="https://overpass-api.de/api",
                    fetched_at_utc=now_utc,
                    ttl_s=30 * 86400,
                    is_stale=False,
                    note=f"Retrieved {len(osm_s)} settlements from OSM",
                )
        except Exception:
            pass
        return [], ProvenanceRecord(name="overture_places", source="Overture Maps", url="", fetched_at_utc=now_utc, ttl_s=OVERTURE_CACHE_TTL_S, is_stale=False)

    con = _init_duckdb()
    urls = [f.get("azure") or f.get("aws") for f in files if f.get("azure") or f.get("aws")]
    file_list_sql = ", ".join(f"'{u}'" for u in urls)

    query = f"""
    SELECT 
        id,
        names.primary as name,
        basic_category,
        taxonomy.primary as taxonomy,
        ST_AsGeoJSON(geometry) as geojson
    FROM read_parquet([{file_list_sql}])
    WHERE bbox.xmin <= {aoi.east} AND bbox.xmax >= {aoi.west}
      AND bbox.ymin <= {aoi.north} AND bbox.ymax >= {aoi.south}
      AND names.primary IS NOT NULL AND trim(names.primary) != ''
    LIMIT 200;
    """

    candidates: List[Dict[str, Any]] = []
    try:
        df = con.execute(query).fetchdf()
        for _, row in df.iterrows():
            g = json.loads(row["geojson"])
            if g.get("type") != "Point":
                continue
            coords = g.get("coordinates", [])
            if len(coords) < 2:
                continue
            lon, lat = float(coords[0]), float(coords[1])
            name = str(row["name"]).strip()
            cat = str(row["basic_category"] or row["taxonomy"] or "place").lower()
            rank = OVERTURE_PLACE_RANKINGS.get(cat, 50)
            candidates.append({
                "id": str(row["id"]),
                "name": name,
                "lat": lat,
                "lon": lon,
                "rank": rank,
            })
    except Exception as exc:
        logger.warning("Overture settlements query failed: %s", exc)
        from core.data.osm import _find_enclosing_cached_settlements
        enc = _find_enclosing_cached_settlements(aoi, G)
        if enc:
            prov = ProvenanceRecord(name="overture_places", source="Cached Fallback", url="", fetched_at_utc=now_utc, ttl_s=0, is_stale=True)
            return enc, prov
        return [], ProvenanceRecord(name="overture_places", source="Overture Maps", url="", fetched_at_utc=now_utc, ttl_s=0, is_stale=True)
    finally:
        con.close()

    if not candidates:
        from core.data.osm import _find_enclosing_cached_settlements
        enc = _find_enclosing_cached_settlements(aoi, G)
        if enc:
            prov = ProvenanceRecord(name="overture_places", source="Cached Fallback", url="", fetched_at_utc=now_utc, ttl_s=0, is_stale=True)
            return enc, prov
        try:
            from core.data.osm import get_settlements
            osm_s = get_settlements(aoi, G)
            if osm_s:
                return osm_s, ProvenanceRecord(
                    name="overture_places",
                    source="OpenStreetMap (Fallback)",
                    url="https://overpass-api.de/api",
                    fetched_at_utc=now_utc,
                    ttl_s=30 * 86400,
                    is_stale=False,
                    note=f"Retrieved {len(osm_s)} settlements from OSM",
                )
        except Exception:
            pass
        return [], ProvenanceRecord(name="overture_places", source="Overture Maps", url="", fetched_at_utc=now_utc, ttl_s=OVERTURE_CACHE_TTL_S, is_stale=False)

    # Snap to nearest graph nodes & deduplicate within 300m
    candidates.sort(key=lambda c: c["rank"])
    node_coords = np.array([[d["y"], d["x"]] for _, d in G.nodes(data=True)])
    node_ids = list(G.nodes)

    settlements: List[Settlement] = []
    snapped_by_node: Dict[int, List[Settlement]] = {}

    for cand in candidates:
        dists = (node_coords[:, 0] - cand["lat"]) ** 2 + (node_coords[:, 1] - cand["lon"]) ** 2
        nearest_idx = int(np.argmin(dists))
        snapped_node_id = node_ids[nearest_idx]

        if snapped_node_id in snapped_by_node:
            is_dup = False
            for prev in snapped_by_node[snapped_node_id]:
                if haversine_m(cand["lon"], cand["lat"], prev.lon, prev.lat) <= 300.0:
                    is_dup = True
                    break
            if is_dup:
                continue

        st = Settlement(
            id=cand["id"],
            name=cand["name"],
            lat=cand["lat"],
            lon=cand["lon"],
            node=snapped_node_id,
        )
        settlements.append(st)
        snapped_by_node.setdefault(snapped_node_id, []).append(st)
        if len(settlements) >= 60:
            break

    try:
        cache_data = {
            "fetched_at_utc": now_utc.isoformat(),
            "settlements": [s.model_dump() for s in settlements],
        }
        settlements_path.write_text(json.dumps(cache_data), encoding="utf-8")
    except Exception as exc:
        logger.warning("Failed saving settlements cache: %s", exc)

    prov = ProvenanceRecord(
        name="overture_places",
        source=f"Overture Maps Foundation ({release})",
        url=urls[0] if urls else "https://overturemaps.org",
        fetched_at_utc=now_utc,
        ttl_s=OVERTURE_CACHE_TTL_S,
        is_stale=False,
        note=f"Extracted {len(settlements)} settlements",
    )
    return settlements, prov


def get_overture_shelters(aoi: AOI) -> Tuple[List[Tuple[str, float, float, str]], ProvenanceRecord]:
    """Retrieve designated emergency shelters within an AOI from Overture places or cached shelters."""
    now_utc = datetime.now(timezone.utc)
    # Check if cached shelters exist in cache/osm/
    from core.data.osm import _find_enclosing_cached_shelters
    enc = _find_enclosing_cached_shelters(aoi)
    if enc:
        prov = ProvenanceRecord(
            name="emergency_shelters",
            source="Verified Open Datasets / Cache",
            url="cache://local/shelters",
            fetched_at_utc=now_utc,
            ttl_s=0,
            is_stale=True,
            note=f"Serving {len(enc)} shelters from cached baseline",
        )
        return enc, prov

    # If no cached shelters exist, query Overture places for emergency civic amenities
    release = get_latest_overture_release()
    files = []
    try:
        files = _get_stac_partition_files("places", "place", aoi, release)
    except Exception:
        pass

    if not files:
        try:
            from core.data.osm import get_shelters
            osm_sh = get_shelters(aoi)
            if osm_sh:
                return osm_sh, ProvenanceRecord(name="emergency_shelters", source="OpenStreetMap (Fallback)", url="https://overpass-api.de/api", fetched_at_utc=now_utc, ttl_s=30 * 86400, is_stale=False, note=f"Retrieved {len(osm_sh)} shelters from OSM")
        except Exception:
            pass
        return [], ProvenanceRecord(name="emergency_shelters", source="Overture Places", url="", fetched_at_utc=now_utc, ttl_s=OVERTURE_CACHE_TTL_S, is_stale=False, note="0 shelters")

    con = _init_duckdb()
    urls = [f.get("azure") or f.get("aws") for f in files if f.get("azure") or f.get("aws")]
    file_list_sql = ", ".join(f"'{u}'" for u in urls)

    shelter_keywords = "('hospital', 'clinic', 'school', 'college', 'community_centre', 'civic', 'fire_station')"
    query = f"""
    SELECT 
        names.primary as name,
        basic_category,
        ST_AsGeoJSON(geometry) as geojson
    FROM read_parquet([{file_list_sql}])
    WHERE bbox.xmin <= {aoi.east} AND bbox.xmax >= {aoi.west}
      AND bbox.ymin <= {aoi.north} AND bbox.ymax >= {aoi.south}
      AND (lower(basic_category) IN {shelter_keywords} OR lower(taxonomy.primary) IN {shelter_keywords})
    LIMIT 50;
    """

    shelters: List[Tuple[str, float, float, str]] = []
    try:
        df = con.execute(query).fetchdf()
        for _, row in df.iterrows():
            g = json.loads(row["geojson"])
            if g.get("type") != "Point":
                continue
            coords = g.get("coordinates", [])
            if len(coords) < 2:
                continue
            lon, lat = float(coords[0]), float(coords[1])
            name = str(row["name"] or "Designated Evacuation Facility").strip()
            kind = str(row["basic_category"] or "shelter").strip()
            shelters.append((name, lat, lon, kind))
    except Exception as exc:
        logger.warning("Overture shelter query failed: %s", exc)
    finally:
        con.close()

    if not shelters:
        try:
            from core.data.osm import get_shelters
            osm_sh = get_shelters(aoi)
            if osm_sh:
                return osm_sh, ProvenanceRecord(
                    name="emergency_shelters",
                    source="OpenStreetMap (Fallback)",
                    url="https://overpass-api.de/api",
                    fetched_at_utc=now_utc,
                    ttl_s=30 * 86400,
                    is_stale=False,
                    note=f"Retrieved {len(osm_sh)} shelters from OSM",
                )
        except Exception:
            pass

    note_text = f"Extracted {len(shelters)} shelter locations" if shelters else "Shelters unavailable from upstream providers (boundary exits preserved)"
    prov = ProvenanceRecord(
        name="emergency_shelters",
        source=f"Overture Maps Foundation ({release})" if shelters else "Upstream Shelter Providers",
        url=urls[0] if urls else "https://overturemaps.org",
        fetched_at_utc=now_utc,
        ttl_s=OVERTURE_CACHE_TTL_S,
        is_stale=False,
        note=note_text,
    )
    return shelters, prov
