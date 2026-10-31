"""Agent operational tools and schemas for EmberRoute orchestrator.

Plain functions returning concise, JSON-serialisable summaries capped at ~300 tokens.
Full simulation results and geometries are saved to orchestrator state and never
passed directly to the LLM.
"""

from contextlib import contextmanager
import json
import logging
import math
from typing import Any, Dict, List, Optional, Tuple

from core.data.firms import fetch_detections
from core.data.weather import fetch_wind_series
from core.models import AOI, PipelineResult
from core.pipeline import PipelineError, run_pipeline

logger = logging.getLogger(__name__)

# Context variable for linking tool executions to active orchestrator state
_CURRENT_TOOL_CONTEXT: Optional[Any] = None


@contextmanager
def set_tool_context(ctx: Any):
    """Context manager setting active orchestrator context for tools."""
    global _CURRENT_TOOL_CONTEXT
    prev = _CURRENT_TOOL_CONTEXT
    _CURRENT_TOOL_CONTEXT = ctx
    try:
        yield
    finally:
        _CURRENT_TOOL_CONTEXT = prev


def get_tool_context() -> Optional[Any]:
    """Retrieve active orchestrator context."""
    return _CURRENT_TOOL_CONTEXT


def estimate_tokens(text: str) -> int:
    """Estimate token count as ceil(len(text) / 4)."""
    return max(1, math.ceil(len(text) / 4.0))


def compact(data: Any, max_tokens: int = 300) -> Any:
    """Recursively prune, truncate, and compact data to stay within token budget.

    - Truncates lists to at most 5 items.
    - Rounds floating point values.
    - Removes large coordinate arrays or internal geometries.
    """
    def _prune(item: Any) -> Any:
        if isinstance(item, dict):
            pruned: Dict[str, Any] = {}
            for k, v in item.items():
                if k in ("route_lonlat", "geometry", "coordinates", "arrival_grid", "arrival_min"):
                    continue
                pruned[k] = _prune(v)
            return pruned
        elif isinstance(item, list):
            if len(item) > 5:
                truncated = [_prune(x) for x in item[:5]]
                truncated.append({"_omitted_count": len(item) - 5})
                return truncated
            return [_prune(x) for x in item]
        elif isinstance(item, float):
            return round(item, 2)
        return item

    cleaned = _prune(data)
    json_str = json.dumps(cleaned, default=str)
    if estimate_tokens(json_str) <= max_tokens:
        return cleaned

    # Secondary trimming if still too large
    if isinstance(cleaned, dict) and "settlements" in cleaned:
        cleaned["settlements"] = cleaned["settlements"][:3]
    return cleaned


def get_fire_detections(aoi: Dict[str, float]) -> Dict[str, Any]:
    """Fetch active satellite fire detections in the given bounding box."""
    try:
        box = AOI(
            west=float(aoi["west"]),
            south=float(aoi["south"]),
            east=float(aoi["east"]),
            north=float(aoi["north"]),
        )
        dets, prov = fetch_detections(box, hours=24)
        total_frp = sum(d.frp for d in dets)
        summary = {
            "count": len(dets),
            "total_frp": round(total_frp, 1),
            "source": prov.source,
            "is_stale": prov.is_stale,
            "detections": [
                {
                    "lat": round(d.lat, 4),
                    "lon": round(d.lon, 4),
                    "frp": round(d.frp, 1),
                    "conf": d.confidence,
                }
                for d in dets[:5]
            ],
        }
        return compact({"status": "ok", "summary": summary})
    except Exception as exc:
        code = getattr(exc, "code", "FEED_DOWN")
        logger.warning("get_fire_detections error: %s", exc)
        return {"error": str(code), "message": str(exc)}


def get_weather(center: Dict[str, float]) -> Dict[str, Any]:
    """Fetch live wind and weather conditions for the center coordinates."""
    try:
        lat = float(center["lat"])
        lon = float(center["lon"])
        wind, prov = fetch_wind_series(lat, lon)
        summary = {
            "speed_ms": round(wind.speed_ms[0], 1) if wind.speed_ms else 0.0,
            "dir_from_deg": round(wind.dir_from_deg[0], 1) if wind.dir_from_deg else 0.0,
            "spread_dir_deg": round((wind.dir_from_deg[0] + 180.0) % 360.0, 1) if wind.dir_from_deg else 0.0,
            "rh_pct": round(wind.rh[0], 1) if wind.rh else 0.0,
            "temp_c": round(wind.temp_c[0], 1) if wind.temp_c else 0.0,
            "is_stale": wind.is_stale,
            "source": wind.source,
        }
        return compact({"status": "ok", "summary": summary})
    except Exception as exc:
        code = getattr(exc, "code", "FEED_DOWN")
        logger.warning("get_weather error: %s", exc)
        return {"error": str(code), "message": str(exc)}


def run_full_plan(
    aoi: Dict[str, float],
    mode: str = "LIVE",
    ignition: Optional[Dict[str, float]] = None,
    wind_override: Optional[Dict[str, float]] = None,
) -> Dict[str, Any]:
    """Execute end-to-end simulation and evacuation routing.

    Stores the full PipelineResult into the orchestrator context.
    """
    try:
        box = AOI(
            west=float(aoi["west"]),
            south=float(aoi["south"]),
            east=float(aoi["east"]),
            north=float(aoi["north"]),
        )
        ign_pt = (float(ignition["lat"]), float(ignition["lon"])) if ignition else None

        res: PipelineResult = run_pipeline(
            aoi=box,
            mode=mode,
            ignition_point=ign_pt,
            wind_override=wind_override,
            bypass_cache=False,
        )

        ctx = get_tool_context()
        if ctx is not None:
            if hasattr(ctx, "state"):
                ctx.state.last_result = res
                ctx.state.aoi = box
                ctx.state.mode = mode
            if hasattr(ctx, "last_result"):
                ctx.last_result = res

        # Build concise summary for LLM consumption
        plans_summary: List[Dict[str, Any]] = []
        for p in res.plans[:5]:
            arr_val = round(p.fire_arrival_min, 1) if (p.fire_arrival_min is not None and math.isfinite(p.fire_arrival_min)) else None
            plans_summary.append({
                "name": p.settlement.name,
                "status": p.status,
                "arrival_min": arr_val,
                "depart_by_min": round(p.depart_by_min, 1) if p.depart_by_min is not None else None,
                "naive_cut": p.naive_cut,
            })

        summary = {
            "mode": res.mode,
            "metrics": res.metrics,
            "settlements_total": len(res.plans),
            "urgent_settlements": plans_summary,
            "warnings": res.warnings[:3],
        }
        return compact({"status": "ok", "summary": summary})
    except Exception as exc:
        code = getattr(exc, "code", "SIMULATION_ERROR")
        logger.warning("run_full_plan error: %s", exc)
        return {"error": str(code), "message": str(exc)}


def get_settlement_detail(name: str) -> Dict[str, Any]:
    """Inspect routing and departure detail for a named settlement from latest plan."""
    ctx = get_tool_context()
    res: Optional[PipelineResult] = getattr(ctx, "last_result", None)
    if res is None and ctx and hasattr(ctx, "state"):
        res = getattr(ctx.state, "last_result", None)

    if not res or not res.plans:
        return {"error": "NO_ACTIVE_PLAN", "message": "No active evacuation plan available in state"}

    target_name = name.strip().lower()
    for p in res.plans:
        if p.settlement.name.lower() == target_name:
            detail = {
                "name": p.settlement.name,
                "status": p.status,
                "fire_arrival_min": round(p.fire_arrival_min, 1) if (p.fire_arrival_min is not None and math.isfinite(p.fire_arrival_min)) else "inf",
                "depart_by_min": round(p.depart_by_min, 1) if p.depart_by_min is not None else None,
                "travel_time_min": round(p.route_travel_min, 1) if p.route_travel_min is not None else None,
                "naive_cut": p.naive_cut,
                "has_route": bool(p.route_lonlat and len(p.route_lonlat) >= 2),
                "note": p.note,
            }
            return compact({"status": "ok", "summary": detail})

    return {"error": "NOT_FOUND", "message": f"Settlement '{name}' not found in active plan"}


def expand_search(aoi_scale: float = 1.3, horizon_min: int = 720) -> Dict[str, Any]:
    """Expand the current AOI and re-run simulation with extended forecast horizon."""
    ctx = get_tool_context()
    if ctx is None or not hasattr(ctx, "state") or ctx.state.aoi is None:
        return {"error": "NO_CONTEXT", "message": "No active AOI context found for expansion"}

    cur_aoi = ctx.state.aoi
    c_lat, c_lon = cur_aoi.center
    half_w = (cur_aoi.east - cur_aoi.west) * aoi_scale / 2.0
    half_h = (cur_aoi.north - cur_aoi.south) * aoi_scale / 2.0

    new_aoi = {
        "west": c_lon - half_w,
        "south": c_lat - half_h,
        "east": c_lon + half_w,
        "north": c_lat + half_h,
    }

    ign = None
    if ctx.state.mode == "SCENARIO" and ctx.state.last_result and ctx.state.last_result.spread.ignitions:
        ign_pt = ctx.state.last_result.spread.ignitions[0]
        ign = {"lat": ign_pt[0], "lon": ign_pt[1]}

    return run_full_plan(
        aoi=new_aoi,
        mode=ctx.state.mode,
        ignition=ign,
        wind_override=None,
    )


TOOL_SCHEMAS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_fire_detections",
            "description": "Fetch active satellite fire detections (NASA FIRMS) within an AOI bounding box.",
            "parameters": {
                "type": "object",
                "properties": {
                    "aoi": {
                        "type": "object",
                        "properties": {
                            "west": {"type": "number", "description": "West longitude"},
                            "south": {"type": "number", "description": "South latitude"},
                            "east": {"type": "number", "description": "East longitude"},
                            "north": {"type": "number", "description": "North latitude"},
                        },
                        "required": ["west", "south", "east", "north"],
                    }
                },
                "required": ["aoi"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Fetch real-time wind speed, wind direction, relative humidity, and temperature.",
            "parameters": {
                "type": "object",
                "properties": {
                    "center": {
                        "type": "object",
                        "properties": {
                            "lat": {"type": "number", "description": "Latitude"},
                            "lon": {"type": "number", "description": "Longitude"},
                        },
                        "required": ["lat", "lon"],
                    }
                },
                "required": ["center"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_full_plan",
            "description": "Run the complete wildfire spread simulation and time-dependent evacuation routing.",
            "parameters": {
                "type": "object",
                "properties": {
                    "aoi": {
                        "type": "object",
                        "properties": {
                            "west": {"type": "number"},
                            "south": {"type": "number"},
                            "east": {"type": "number"},
                            "north": {"type": "number"},
                        },
                        "required": ["west", "south", "east", "north"],
                    },
                    "mode": {
                        "type": "string",
                        "enum": ["LIVE", "SCENARIO"],
                        "description": "Operational mode",
                    },
                    "ignition": {
                        "type": "object",
                        "properties": {
                            "lat": {"type": "number"},
                            "lon": {"type": "number"},
                        },
                    },
                    "wind_override": {
                        "type": "object",
                        "properties": {
                            "speed_ms": {"type": "number"},
                            "dir_from_deg": {"type": "number"},
                        },
                    },
                },
                "required": ["aoi"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_settlement_detail",
            "description": "Get detailed evacuation departure time, status, and travel time for a specific settlement.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Name of the settlement"},
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "expand_search",
            "description": "Expand search area and extend horizon when no settlements are threatened despite active fire.",
            "parameters": {
                "type": "object",
                "properties": {
                    "aoi_scale": {"type": "number", "description": "Expansion multiplier, default 1.3"},
                    "horizon_min": {"type": "integer", "description": "Simulation horizon in minutes, default 720"},
                },
            },
        },
    },
]
