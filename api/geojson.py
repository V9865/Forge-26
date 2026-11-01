"""GeoJSON converters translating simulation results into API contract schemas.

Handles detections, arrival isochrone polygons, settlement statuses,
and evacuation route LineStrings with coordinates rounded to 5 decimal places.
"""

import math
from typing import Any, Dict, List, Optional
from core.fire.bands import arrival_bands
from core.models import PipelineResult, SpreadResult


def _round_coord(val: float, decimals: int = 5) -> float:
    return round(float(val), decimals)


def _round_coords_list(coords: Any, decimals: int = 5) -> Any:
    if isinstance(coords, (tuple, list)) and len(coords) > 0:
        if isinstance(coords[0], (int, float)):
            return [_round_coord(c, decimals) for c in coords]
        return [_round_coords_list(sub, decimals) for sub in coords]
    return coords


def build_detections_geojson(result: PipelineResult) -> Dict[str, Any]:
    """Convert satellite fire detections into a GeoJSON FeatureCollection."""
    features: List[Dict[str, Any]] = []
    for d in result.detections:
        feat = {
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [_round_coord(d.lon), _round_coord(d.lat)],
            },
            "properties": {
                "acq_time_utc": d.acq_time_utc.isoformat(),
                "frp": round(float(d.frp), 2),
                "confidence": d.confidence,
                "satellite": d.satellite,
            },
        }
        features.append(feat)

    return {"type": "FeatureCollection", "features": features}


def build_arrival_bands_geojson(spread: Optional[SpreadResult], step_min: int = 30) -> Dict[str, Any]:
    """Extract cumulative vector arrival isochrone polygons using core.fire.bands."""
    if spread is None:
        return {"type": "FeatureCollection", "features": []}

    try:
        raw_bands = arrival_bands(spread, step_min=step_min)
        features: List[Dict[str, Any]] = []
        for band in raw_bands:
            features.append({
                "type": "Feature",
                "geometry": _round_coords_list(band["geometry"], 5),
                "properties": {
                    "t_min": band["t_min"],
                },
            })
        return {"type": "FeatureCollection", "features": features}
    except Exception:
        return {"type": "FeatureCollection", "features": []}


def build_settlements_geojson(result: PipelineResult) -> Dict[str, Any]:
    """Convert evaluated settlement plans into a GeoJSON FeatureCollection."""
    features: List[Dict[str, Any]] = []
    for plan in result.plans:
        s = plan.settlement
        arr_val = round(plan.fire_arrival_min, 1) if (plan.fire_arrival_min is not None and math.isfinite(plan.fire_arrival_min)) else None
        dep_val = round(plan.depart_by_min, 1) if plan.depart_by_min is not None else None
        tt_val = round(plan.route_travel_min, 1) if plan.route_travel_min is not None else None

        feat = {
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [_round_coord(s.lon), _round_coord(s.lat)],
            },
            "properties": {
                "id": s.id,
                "name": s.name,
                "status": plan.status,
                "fire_arrival_min": arr_val,
                "depart_by_min": dep_val,
                "route_travel_min": tt_val,
                "naive_cut": plan.naive_cut,
                "note": plan.note,
            },
        }
        features.append(feat)

    return {"type": "FeatureCollection", "features": features}


def build_roads_geojson(result: PipelineResult) -> Dict[str, Any]:
    """Convert transportation road segments into a valid GeoJSON FeatureCollection."""
    raw_roads = getattr(result, "roads", []) or []
    features: List[Dict[str, Any]] = []
    for r in raw_roads:
        if isinstance(r, dict) and r.get("type") == "Feature":
            geom = r.get("geometry")
            if geom and "coordinates" in geom:
                features.append({
                    "type": "Feature",
                    "geometry": {
                        "type": geom.get("type", "LineString"),
                        "coordinates": _round_coords_list(geom.get("coordinates", []), 5),
                    },
                    "properties": r.get("properties", {"feature_type": "road"}),
                })
    return {"type": "FeatureCollection", "features": features}


def build_routes_geojson(result: PipelineResult) -> Dict[str, Any]:
    """Convert calculated evacuation route geometries into a GeoJSON FeatureCollection."""
    features: List[Dict[str, Any]] = []
    for plan in result.plans:
        if plan.route_lonlat and len(plan.route_lonlat) >= 2:
            coords = [[round(float(pt[0]), 5), round(float(pt[1]), 5)] for pt in plan.route_lonlat]
            feat = {
                "type": "Feature",
                "geometry": {
                    "type": "LineString",
                    "coordinates": coords,
                },
                "properties": {
                    "settlement_id": plan.settlement.id,
                    "settlement_name": plan.settlement.name,
                    "kind": "aware",
                    "cut": False,
                },
            }
            features.append(feat)

    return {"type": "FeatureCollection", "features": features}


def build_naive_cut_segments_geojson(result: PipelineResult) -> Dict[str, Any]:
    """Convert naive route segments cut by fire into a GeoJSON FeatureCollection."""
    features: List[Dict[str, Any]] = []
    for plan in result.plans:
        cut_coords = plan.naive_route_lonlat or []
        if plan.naive_cut and cut_coords and len(cut_coords) >= 2:
            coords = [[round(float(pt[0]), 5), round(float(pt[1]), 5)] for pt in cut_coords]
            features.append({
                "type": "Feature",
                "geometry": {
                    "type": "LineString",
                    "coordinates": coords,
                },
                "properties": {
                    "settlement_id": plan.settlement.id,
                    "settlement_name": plan.settlement.name,
                    "kind": "baseline_cut",
                    "cut": True,
                },
            })

    return {"type": "FeatureCollection", "features": features}


