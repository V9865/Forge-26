"""Acceptance verification script for EmberRoute evacuation solver and pipeline.

Runs run_pipeline on an AOI in SCENARIO mode with ignition near multiple villages,
prints comprehensive metrics and the first 5 settlement evacuation plans,
and renders an evacuation map PNG showing arrival bands, road fire risk,
settlement risk statuses, and safe routes.
"""

from pathlib import Path
import sys
import time

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

import matplotlib.pyplot as plt
import numpy as np

from core.models import AOI
from core.pipeline import run_pipeline


def run_acceptance() -> None:
    # 0.20 x 0.15 degree area in the Rhone Valley / Valais alpine region (Sion/Sierre corridor)
    aoi = AOI(west=7.45, south=46.20, east=7.65, north=46.35)
    # Ignition placed in the eastern hills, spreading west-northwest with wind
    # Western half of the valley (Sion / Sierre) remains unburned and provides safe targets & shelters
    ignition = (46.31, 7.62)
    wind = {"speed_ms": 5.0, "dir_from_deg": 120.0}

    print("=" * 70)
    print("EMBERROUTE EVACUATION SOLVER & PIPELINE ACCEPTANCE RUN")
    print(f"AOI: West={aoi.west}, South={aoi.south}, East={aoi.east}, North={aoi.north}")
    print(f"Mode: SCENARIO | Ignition: {ignition} | Wind: 8.0 m/s from 250°")
    print("=" * 70)

    t0 = time.perf_counter()
    result = run_pipeline(
        aoi=aoi,
        mode="SCENARIO",
        ignition_point=ignition,
        wind_override=wind,
    )
    total_pipeline_time = time.perf_counter() - t0

    # 1. Print metrics
    metrics = result.metrics
    print("\n--- Pipeline Execution Metrics ---")
    print(f"Total Pipeline Runtime:   {total_pipeline_time:.2f} s")
    print(f"Total Settlements:        {metrics.get('n_settlements_total')}")
    print(f"Total Shelters:           {metrics.get('n_shelters_total')}")
    print(f"Threatened Settlements:   {metrics.get('n_threatened')}")
    print(f"  - EVACUATE:             {metrics.get('n_evacuate')}")
    print(f"  - TRAPPED:              {metrics.get('n_trapped')}")
    print(f"  - ALREADY_BURNING:      {metrics.get('n_already_burning')}")
    print(f"Naive Routes Cut by Fire: {metrics.get('n_naive_cut')}")
    print(f"Rescued by Fire-Aware:    {metrics.get('n_rescued_by_replan')}")
    med_dep = metrics.get('median_depart_by_min')
    min_dep = metrics.get('min_depart_by_min')
    print(f"Median Departure Deadline: {med_dep:.1f} min" if med_dep else "Median Departure Deadline: N/A")
    print(f"Earliest Departure Deadline: {min_dep:.1f} min" if min_dep else "Earliest Departure Deadline: N/A")

    # 2. Print execution trace timings
    print("\n--- Execution Stage Timings ---")
    for step in result.trace:
        print(f"  {step['stage']:<30} {step['duration_s']:>7.3f} s")

    # 3. Print first 5 settlement plans
    print("\n--- Settlement Plans (First 5) ---")
    for i, plan in enumerate(result.plans[:5]):
        s = plan.settlement
        arr_str = f"{plan.fire_arrival_min:.1f} min" if plan.fire_arrival_min else "inf"
        dep_str = f"{plan.depart_by_min:.1f} min" if plan.depart_by_min is not None else "N/A"
        trav_str = f"{plan.route_travel_min:.1f} min" if plan.route_travel_min else "N/A"
        print(f"[{i+1}] {s.name:<22} Status={plan.status:<14} FireArrival={arr_str:<10} DepartBy={dep_str:<10} Travel={trav_str:<10} NaiveCut={plan.naive_cut}")

    # 4. Generate and save visualization PNG
    debug_dir = Path(".cache") / "debug"
    debug_dir.mkdir(parents=True, exist_ok=True)
    out_png = debug_dir / "evacuation_plan_debug.png"

    print(f"\nRendering debug visualization to {out_png}...")
    fig, ax = plt.subplots(figsize=(12, 10), dpi=180)

    # (a) Plot fire arrival contours
    spread_grid = result.spread.grid
    arr_grid = np.copy(result.spread.arrival_min)
    arr_masked = np.ma.masked_where(arr_grid >= 720.0, arr_grid)

    from core.geo import cell_centers_lonlat
    grid_lons, grid_lats = cell_centers_lonlat(spread_grid)

    if np.any(~arr_masked.mask):
        cf = ax.contourf(grid_lons, grid_lats, arr_masked, levels=12, cmap="YlOrRd", alpha=0.5, zorder=1)
        cbar = plt.colorbar(cf, ax=ax, fraction=0.035, pad=0.02)
        cbar.set_label("Fire Arrival Time (minutes)", fontsize=9)

    # (b) Plot ignition point
    ax.scatter([ignition[1]], [ignition[0]], color="black", marker="*", s=160, label="Ignition Point", zorder=6)

    # (c) Plot safe evacuation routes
    for plan in result.plans:
        if plan.status == "EVACUATE" and plan.route_lonlat and len(plan.route_lonlat) >= 2:
            r_lons = [pt[0] for pt in plan.route_lonlat]
            r_lats = [pt[1] for pt in plan.route_lonlat]
            ax.plot(r_lons, r_lats, color="#059669", linewidth=2.0, alpha=0.85, zorder=4)

    # (d) Plot settlements by status
    status_colors = {
        "EVACUATE": "#10b981",       # Emerald green
        "TRAPPED": "#ef4444",        # Red
        "ALREADY_BURNING": "#7f1d1d", # Dark red
        "NOT_THREATENED": "#94a3b8", # Slate
    }

    status_labels = set()
    for plan in result.plans:
        s = plan.settlement
        col = status_colors.get(plan.status, "#6b7280")
        label = plan.status if plan.status not in status_labels else None
        if label:
            status_labels.add(label)

        ax.scatter(s.lon, s.lat, color=col, s=45, edgecolors="black", linewidths=0.6, label=label, zorder=5)
        if plan.status in ("EVACUATE", "TRAPPED"):
            dep_note = f" (dep: {plan.depart_by_min:.0f}m)" if plan.depart_by_min else ""
            ax.annotate(f"{s.name}{dep_note}", (s.lon, s.lat), fontsize=7, fontweight="bold",
                        xytext=(3, 3), textcoords="offset points", color="#1e293b", zorder=7)

    ax.set_title(f"EmberRoute Evacuation Analysis (Valais Alpine Corridor)\nThreatened: {metrics.get('n_threatened')} | Evacuate: {metrics.get('n_evacuate')} | Trapped: {metrics.get('n_trapped')} | Rescued: {metrics.get('n_rescued_by_replan')}", fontsize=11, fontweight="bold")
    ax.set_xlabel("Longitude (°)")
    ax.set_ylabel("Latitude (°)")
    ax.legend(loc="lower right", fontsize=8)
    ax.grid(True, linestyle="--", alpha=0.3)
    plt.tight_layout()
    plt.savefig(out_png)
    plt.close()

    print(f"Debug PNG saved: {out_png} ({out_png.stat().st_size / 1024:.1f} KB)")
    print("=" * 70)


if __name__ == "__main__":
    run_acceptance()

