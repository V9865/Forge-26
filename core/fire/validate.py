"""Wildfire spread validation and empirical calibration against NASA FIRMS archive observations.

Evaluates simulation recall, burned area, and directional centroid accuracy
against real historical satellite fire detections and Open-Meteo weather records.
"""

from datetime import datetime, timedelta, timezone
import io
import json
import logging
import math
from pathlib import Path
import time
from typing import Any, Dict, List, Optional, Set, Tuple
import httpx
import numpy as np
import pandas as pd
from scipy.ndimage import binary_dilation

from core.cache import cached_or_fetch
from core.config import get_settings
from core.data.firms import parse_firms_csv
from core.data.weather import fetch_wind_history
from core.fire.baseline import isotropic_baseline
from core.fire.spread import ignitions_from_detections, simulate_spread
from core.geo import bearing_deg, haversine_m, lonlat_to_rc, rc_to_lonlat
from core.layers import build_layers
from core.models import AOI, FireDetection, Layers, SpreadParams, SpreadResult, WindSeries

logger = logging.getLogger(__name__)

FIRMS_PUBLIC_7D_URL = "https://firms.modaps.eosdis.nasa.gov/data/active_fire/suomi-npp-viirs-c2/csv/SUOMI_VIIRS_C2_Global_7d.csv"
CALIBRATED_PARAMS_PATH = Path("docs/calibrated_params.json")


_GLOBAL_7D_DF: Optional[pd.DataFrame] = None


def get_global_7d_df() -> Tuple[pd.DataFrame, str]:
    """Load the NASA FIRMS 7-day global active fire archive dataset, cached on disk and in memory."""
    global _GLOBAL_7D_DF
    if _GLOBAL_7D_DF is not None:
        return _GLOBAL_7D_DF, FIRMS_PUBLIC_7D_URL

    cache_key = "firms:global_7d_archive_raw"

    def _do_fetch() -> Tuple[bytes, str, str]:
        logger.info("Downloading official NASA FIRMS 7-day global archive CSV...")
        with httpx.Client(timeout=90.0) as client:
            resp = client.get(FIRMS_PUBLIC_7D_URL)
            if resp.status_code != 200:
                raise RuntimeError(f"HTTP {resp.status_code} downloading FIRMS 7d CSV")
            return resp.content, "NASA FIRMS Global 7d Archive", FIRMS_PUBLIC_7D_URL

    content_bytes, prov = cached_or_fetch(
        key=cache_key,
        ttl_s=86400 * 3,  # 3 days TTL for historical data
        fetch_fn=_do_fetch,
        allow_stale=True,
    )
    _GLOBAL_7D_DF = pd.read_csv(io.BytesIO(content_bytes))
    return _GLOBAL_7D_DF, prov.url


def load_calibrated_params() -> SpreadParams:
    """Load calibrated SpreadParams from docs/calibrated_params.json if available."""
    if CALIBRATED_PARAMS_PATH.exists():
        try:
            data = json.loads(CALIBRATED_PARAMS_PATH.read_text(encoding="utf-8"))
            return SpreadParams(
                k_wind=data.get("k_wind", 0.25),
                midflame=data.get("midflame", 0.5),
                ros_scale=data.get("ros_scale", 1.0),
                lb_cap=data.get("lb_cap", 8.0),
                horizon_min=data.get("horizon_min", 720),
            )
        except Exception as e:
            logger.warning("Could not read calibrated_params.json: %s", e)
    return SpreadParams()


def fetch_archive_detections_for_aoi(
    aoi: AOI, start_dt: datetime, end_dt: datetime
) -> Tuple[List[FireDetection], List[str]]:
    """Fetch real historical satellite fire detections within an AOI and time window.

    Queries the FIRMS 7-day global archive or REST API and parses real detections.

    Args:
        aoi: Area of Interest bounding box.
        start_dt: Beginning of observation window (UTC).
        end_dt: End of observation window (UTC).

    Returns:
        Tuple of (detections_list, provenance_urls).
    """
    settings = get_settings()
    map_key = settings.FIRMS_MAP_KEY.strip()

    df: pd.DataFrame
    prov_url: str

    if map_key:
        cache_key = f"firms:archive:{aoi.west:.4f},{aoi.south:.4f},{aoi.east:.4f},{aoi.north:.4f}:{start_dt.strftime('%Y%m%d')}_{end_dt.strftime('%Y%m%d')}"

        def _do_fetch() -> Tuple[bytes, str, str]:
            day_range = max(1, min(5, math.ceil((end_dt - start_dt).total_seconds() / 86400.0)))
            date_str = end_dt.strftime("%Y-%m-%d")
            url = f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/{map_key}/VIIRS_SNPP_NRT/{aoi.west:.4f},{aoi.south:.4f},{aoi.east:.4f},{aoi.north:.4f}/{day_range}/{date_str}"
            masked_url = url.replace(map_key, "***")
            with httpx.Client(timeout=settings.HTTP_TIMEOUT_S) as client:
                resp = client.get(url)
                if resp.status_code == 200 and not resp.text.strip().lower().startswith("<!doctype"):
                    return resp.content, "NASA FIRMS API", masked_url
            raise RuntimeError("FIRMS area fetch failed or empty")

        try:
            content_bytes, prov = cached_or_fetch(
                key=cache_key,
                ttl_s=86400 * 3,
                fetch_fn=_do_fetch,
                allow_stale=True,
            )
            df = pd.read_csv(io.BytesIO(content_bytes))
            prov_url = prov.url
        except Exception:
            df, prov_url = get_global_7d_df()
    else:
        df, prov_url = get_global_7d_df()

    if df.empty or "latitude" not in df.columns:
        return [], [prov_url]

    # Filter bounding box
    in_bbox = (
        (df["latitude"] >= aoi.south)
        & (df["latitude"] <= aoi.north)
        & (df["longitude"] >= aoi.west)
        & (df["longitude"] <= aoi.east)
    )
    df_aoi = df[in_bbox]

    detections: List[FireDetection] = []
    for _, row in df_aoi.iterrows():
        try:
            raw_conf = str(row.get("confidence", "")).strip().lower()
            if raw_conf not in {"n", "h", "nominal", "high"}:
                continue

            acq_date_str = str(row["acq_date"]).strip()
            acq_time_str = str(row["acq_time"]).strip().split(".")[0].zfill(4)
            acq_dt = datetime.strptime(f"{acq_date_str} {acq_time_str}", "%Y-%m-%d %H%M").replace(
                tzinfo=timezone.utc
            )

            if start_dt <= acq_dt <= end_dt:
                detections.append(
                    FireDetection(
                        lat=float(row["latitude"]),
                        lon=float(row["longitude"]),
                        acq_time_utc=acq_dt,
                        frp=float(row.get("frp", 0.0)),
                        confidence=raw_conf,
                        satellite=str(row.get("satellite", "VIIRS")).strip(),
                    )
                )
        except Exception:
            continue

    return sorted(detections, key=lambda d: d.acq_time_utc), [prov_url]


def find_candidate_events(days_back: int = 8, min_detections: int = 25, min_days: int = 2) -> List[Dict[str, Any]]:
    """Scan NASA FIRMS archive for candidate multi-day active wildfire events.

    Args:
        days_back: Number of days to inspect.
        min_detections: Minimum total detections for an event cluster.
        min_days: Minimum distinct calendar days spanned.

    Returns:
        List of candidate event dictionaries with bounding box, date range, and suggested T0.
    """
    cache_key = "firms:global_7d:candidate_scan"

    def _do_fetch() -> Tuple[bytes, str, str]:
        with httpx.Client(timeout=60.0) as client:
            resp = client.get(FIRMS_PUBLIC_7D_URL)
            if resp.status_code != 200:
                raise RuntimeError(f"HTTP {resp.status_code} downloading FIRMS 7d CSV")
            return resp.content, "NASA FIRMS Global 7d Archive", FIRMS_PUBLIC_7D_URL

    content_bytes, _ = cached_or_fetch(
        key=cache_key,
        ttl_s=86400,
        fetch_fn=_do_fetch,
        allow_stale=True,
    )

    df = pd.read_csv(io.StringIO(content_bytes.decode("utf-8", errors="replace")))
    df = df[df["confidence"].isin(["n", "h", "nominal", "high"])]

    # 0.25-degree grid binning
    bin_size = 0.25
    df["r_bin"] = np.floor(df["latitude"] / bin_size).astype(int)
    df["c_bin"] = np.floor(df["longitude"] / bin_size).astype(int)

    grouped = (
        df.groupby(["r_bin", "c_bin"])
        .agg(
            count=("latitude", "count"),
            total_frp=("frp", "sum"),
            min_lat=("latitude", "min"),
            max_lat=("latitude", "max"),
            min_lon=("longitude", "min"),
            max_lon=("longitude", "max"),
            min_date=("acq_date", "min"),
            max_date=("acq_date", "max"),
            n_days=("acq_date", "nunique"),
        )
        .reset_index()
    )

    candidates = grouped[
        (grouped["n_days"] >= min_days) & (grouped["count"] >= min_detections)
    ].sort_values("total_frp", ascending=False)

    results: List[Dict[str, Any]] = []

    for idx, row in candidates.iterrows():
        c_lat = (row["min_lat"] + row["max_lat"]) / 2.0
        c_lon = (row["min_lon"] + row["max_lon"]) / 2.0

        # Suggested AOI: 0.22 x 0.22 degrees around cluster centroid (conforming to max 0.6 deg limit)
        west = round(c_lon - 0.11, 4)
        east = round(c_lon + 0.11, 4)
        south = round(c_lat - 0.11, 4)
        north = round(c_lat + 0.11, 4)

        # Suggested T0: 12:00 UTC on the second active date
        min_d_dt = datetime.strptime(row["min_date"], "%Y-%m-%d").replace(tzinfo=timezone.utc)
        suggested_t0 = (min_d_dt + timedelta(days=1, hours=12)).strftime("%Y-%m-%dT12:00:00Z")

        results.append({
            "name": f"Event_{row['r_bin']}_{row['c_bin']}",
            "center_lat": round(c_lat, 4),
            "center_lon": round(c_lon, 4),
            "detection_count": int(row["count"]),
            "days_spanned": int(row["n_days"]),
            "date_range": f"{row['min_date']} to {row['max_date']}",
            "total_frp": round(float(row["total_frp"]), 1),
            "suggested_t0_utc": suggested_t0,
            "aoi": {
                "west": west,
                "south": south,
                "east": east,
                "north": north,
            },
            "note": f"Multi-day cluster with {int(row['count'])} detections across {int(row['n_days'])} days",
        })

    return results


def load_validation_events(events_path: Path) -> List[Dict[str, Any]]:
    """Load and validate events from JSON file.

    Raises:
        ValueError: If fewer than 3 events are provided.
    """
    if not events_path.exists():
        raise FileNotFoundError(f"Validation events file not found: {events_path}")

    data = json.loads(events_path.read_text(encoding="utf-8"))
    if not isinstance(data, list) or len(data) < 3:
        raise ValueError(
            f"Validation requires at least 3 events in {events_path}, found {len(data) if isinstance(data, list) else 0}."
        )

    return data


def prepare_event_context(event: Dict[str, Any]) -> Dict[str, Any]:
    """Pre-fetch data and spatial layers for an event once to accelerate calibration and evaluation."""
    aoi = AOI(**event["aoi"])
    t0_str = event["t0_utc"].replace("Z", "+00:00")
    t0 = datetime.fromisoformat(t0_str)

    ign_start = t0 - timedelta(hours=18)
    ign_end = t0
    future_start = t0 + timedelta(hours=3)
    future_end = t0 + timedelta(hours=24)

    all_dets, prov_firms = fetch_archive_detections_for_aoi(aoi, ign_start, future_end)

    ign_dets = [d for d in all_dets if ign_start <= d.acq_time_utc <= ign_end]
    future_dets = [d for d in all_dets if future_start < d.acq_time_utc <= future_end]

    layers, prov_layers, _ = build_layers(aoi)

    try:
        ignitions = ignitions_from_detections(layers, ign_dets)
    except ValueError:
        if all_dets:
            ignitions = ignitions_from_detections(layers, all_dets[:5])
        else:
            center_lat, center_lon = aoi.center
            r_c, c_c = lonlat_to_rc(layers.grid, center_lon, center_lat)
            ignitions = [(int(round(r_c)), int(round(c_c)), 0.0)]

    # Filter ignitions within grid bounds
    ignitions = [(r, c, t) for r, c, t in ignitions if 0 <= r < layers.grid.ny and 0 <= c < layers.grid.nx]
    if not ignitions:
        center_lat, center_lon = aoi.center
        r_c, c_c = lonlat_to_rc(layers.grid, center_lon, center_lat)
        ignitions = [(int(round(r_c)), int(round(c_c)), 0.0)]

    start_d = t0.strftime("%Y-%m-%d")
    end_d = (t0 + timedelta(days=2)).strftime("%Y-%m-%d")
    wind, prov_wind = fetch_wind_history(aoi.center[0], aoi.center[1], start_d, end_d)

    # Correct hour alignment from t0
    idx_t0 = max(0, int((t0 - wind.start_utc).total_seconds() // 3600))
    speed_24 = list(wind.speed_ms[idx_t0 : idx_t0 + 24])
    dir_24 = list(wind.dir_from_deg[idx_t0 : idx_t0 + 24])
    rh_24 = list(wind.rh[idx_t0 : idx_t0 + 24])
    temp_24 = list(wind.temp_c[idx_t0 : idx_t0 + 24])

    while len(speed_24) < 24:
        speed_24.append(speed_24[-1] if speed_24 else 5.0)
        dir_24.append(dir_24[-1] if dir_24 else 270.0)
        rh_24.append(rh_24[-1] if rh_24 else 30.0)
        temp_24.append(temp_24[-1] if temp_24 else 25.0)

    wind_slice = WindSeries(
        start_utc=t0,
        speed_ms=speed_24,
        dir_from_deg=dir_24,
        rh=rh_24,
        temp_c=temp_24,
        source="Open-Meteo Archive",
        fetched_at_utc=prov_wind.fetched_at_utc,
    )

    n_future = len(future_dets)
    if n_future > 0:
        lats_f = [d.lat for d in future_dets]
        lons_f = [d.lon for d in future_dets]
        d_lat_km = (max(lats_f) - min(lats_f)) * 111.0
        d_lon_km = (max(lons_f) - min(lons_f)) * 111.0 * math.cos(math.radians(aoi.center[0]))
        hull_area_ha = max(50.0, (d_lat_km * d_lon_km * 100.0) * 0.7)
    else:
        hull_area_ha = 100.0

    return {
        "event": event,
        "aoi": aoi,
        "t0": t0,
        "layers": layers,
        "wind_slice": wind_slice,
        "ignitions": ignitions,
        "future_dets": future_dets,
        "hull_area_ha": hull_area_ha,
        "provenance": [prov_firms[0], prov_wind.url, prov_layers[0].url, prov_layers[1].url],
    }


def evaluate_event(
    event: Dict[str, Any],
    params: SpreadParams,
    ctx: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Execute complete historical validation evaluation for a single event.

    Args:
        event: Event dictionary containing name, aoi, and t0_utc.
        params: Simulation physics parameters to evaluate.
        ctx: Optional pre-loaded context data from prepare_event_context.

    Returns:
        Dictionary with event evaluation metrics:
        - model_recall, baseline_recall, predicted_area_ha, bearing_error_deg, future_count.
    """
    if ctx is None:
        ctx = prepare_event_context(event)

    aoi = ctx["aoi"]
    t0 = ctx["t0"]
    layers = ctx["layers"]
    wind_slice = ctx["wind_slice"]
    ignitions = ctx["ignitions"]
    future_dets = ctx["future_dets"]
    hull_area_ha = ctx["hull_area_ha"]
    prov_urls = ctx["provenance"]

    # Simulate model spread with 24h horizon
    sim_params = params.model_copy(update={"horizon_min": 1440})
    result = simulate_spread(layers, wind_slice, ignitions, sim_params)
    arrival = result.arrival_min
    res_m = float(layers.grid.res_m)

    # Metric 2: Predicted burned area (ha) at 24h
    burned_cells_24h = arrival <= 1440.0
    pred_area_ha = float(np.sum(burned_cells_24h) * (res_m * res_m) / 10000.0)

    # Metric 1: Recall on future detections
    hits_model = 0
    hits_baseline = 0
    ny, nx = arrival.shape

    # Baseline: isotropic baseline matching same predicted area at 24h
    baseline_result, _ = isotropic_baseline(
        layers, ignitions, target_area_ha=max(10.0, pred_area_ha), horizon_min=1440.0
    )
    arrival_base = baseline_result.arrival_min

    for d in future_dets:
        t_delta_min = (d.acq_time_utc - t0).total_seconds() / 60.0
        if t_delta_min <= 0:
            continue

        r_f, c_f = lonlat_to_rc(layers.grid, d.lon, d.lat)
        r = int(round(r_f))
        c = int(round(c_f))

        if 0 <= r < ny and 0 <= c < nx:
            # 1-cell dilation accounts for VIIRS 375m sensor footprint
            mask_model = binary_dilation(arrival <= t_delta_min)
            if mask_model[r, c]:
                hits_model += 1

            mask_base = binary_dilation(arrival_base <= t_delta_min)
            if mask_base[r, c]:
                hits_baseline += 1

    n_future = len(future_dets)
    model_recall = (hits_model / n_future) if n_future > 0 else 0.0
    baseline_recall = (hits_baseline / n_future) if n_future > 0 else 0.0

    # Metric 3: Bearing difference between observed and predicted centroid displacement
    bearing_err_deg: Optional[float] = None
    if n_future >= 5 and np.any(burned_cells_24h):
        obs_mean_lat = float(np.mean([d.lat for d in future_dets]))
        obs_mean_lon = float(np.mean([d.lon for d in future_dets]))

        r_ign_m = float(np.mean([ig[0] for ig in ignitions]))
        c_ign_m = float(np.mean([ig[1] for ig in ignitions]))

        coords_burned = np.argwhere(burned_cells_24h)
        pred_r_m = float(np.mean(coords_burned[:, 0]))
        pred_c_m = float(np.mean(coords_burned[:, 1]))

        r_obs, c_obs = lonlat_to_rc(layers.grid, obs_mean_lon, obs_mean_lat)
        obs_bearing = float(bearing_deg(r_obs - r_ign_m, c_obs - c_ign_m))
        pred_bearing = float(bearing_deg(pred_r_m - r_ign_m, pred_c_m - c_ign_m))

        diff = abs(obs_bearing - pred_bearing) % 360.0
        bearing_err_deg = round(min(diff, 360.0 - diff), 1)

    return {
        "event_name": event["name"],
        "aoi": aoi,
        "grid_str": f"{layers.grid.nx}x{layers.grid.ny} ({layers.grid.res_m:.0f}m)",
        "future_count": n_future,
        "model_recall": round(model_recall, 3),
        "baseline_recall": round(baseline_recall, 3),
        "predicted_area_ha": round(pred_area_ha, 1),
        "hull_area_ha": round(hull_area_ha, 1),
        "bearing_error_deg": bearing_err_deg,
        "result": result,
        "layers": layers,
        "future_dets": future_dets,
        "ignitions": ignitions,
        "provenance": prov_urls,
    }


def calibrate_parameters(train_events: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Perform grid search calibration on the first two events.

    Grid search search space:
    - k_wind in {0.1, 0.25, 0.4}
    - midflame in {0.3, 0.5, 0.7}
    - ros_scale in {0.5, 1.0, 1.5, 2.0}

    Objective:
    Maximise mean recall subject to pred_area <= 3.0 * hull_area to prevent trivially oversized predictions.

    Returns:
        Best calibrated parameter dictionary.
    """
    logger.info("Preparing data for %d training events...", len(train_events))
    train_ctxs = [prepare_event_context(ev) for ev in train_events]
    logger.info("Starting calibration grid search across 36 parameter sets...")

    k_wind_vals = [0.1, 0.25, 0.4]
    midflame_vals = [0.3, 0.5, 0.7]
    ros_scale_vals = [0.5, 1.0, 1.5, 2.0]

    best_score = -1.0
    best_params = {
        "k_wind": 0.25,
        "midflame": 0.5,
        "ros_scale": 1.0,
        "lb_cap": 8.0,
        "horizon_min": 720,
    }

    for kw in k_wind_vals:
        for mf in midflame_vals:
            for rs in ros_scale_vals:
                trial_params = SpreadParams(k_wind=kw, midflame=mf, ros_scale=rs)
                recalls = []
                valid_areas = True

                for ctx in train_ctxs:
                    res = evaluate_event(ctx["event"], trial_params, ctx=ctx)
                    recalls.append(res["model_recall"])
                    if res["predicted_area_ha"] > 3.0 * res["hull_area_ha"]:
                        valid_areas = False

                mean_rec = float(np.mean(recalls)) if recalls else 0.0
                score = mean_rec if valid_areas else (mean_rec * 0.5)

                if score > best_score:
                    best_score = score
                    best_params = {
                        "k_wind": kw,
                        "midflame": mf,
                        "ros_scale": rs,
                        "lb_cap": 8.0,
                        "horizon_min": 720,
                    }

    logger.info("Calibrated optimal parameters: %s (score: %.3f)", best_params, best_score)

    CALIBRATED_PARAMS_PATH.parent.mkdir(parents=True, exist_ok=True)
    CALIBRATED_PARAMS_PATH.write_text(json.dumps(best_params, indent=2), encoding="utf-8")
    return best_params
