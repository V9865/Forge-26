"""Render wildfire spread simulation with hillshade, arrival bands, ignitions, and wind arrow.

CLI usage:
    python scripts/render_spread.py --west -120.2 --south 38.1 --east -120.0 --north 38.3
    python scripts/render_spread.py --west -120.2 --south 38.1 --east -120.0 --north 38.3 --ign-lat 38.15 --ign-lon -120.15
"""

import argparse
from pathlib import Path
import sys
import time

# Ensure repository root is on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import matplotlib.patches as mpatches
from matplotlib.colors import LightSource, ListedColormap
import matplotlib.pyplot as plt
import numpy as np

from core.data.firms import fetch_detections
from core.data.weather import fetch_wind_series
from core.fire.spread import ignition_from_point, ignitions_from_detections, simulate_spread, stats
from core.layers import build_layers
from core.models import AOI, SpreadParams


def render_spread_map(
    layers,
    result,
    wind,
    ignitions,
    sim_stats,
    output_path: Path,
) -> None:
    """Render high-resolution figure of fire spread arrival contours over terrain."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    elev = layers.elevation
    arrival = result.arrival_min
    grid = layers.grid

    fig, ax = plt.subplots(figsize=(10, 8), dpi=150)

    # 1. Background hillshade
    ls = LightSource(azdeg=315, altdeg=45)
    if np.max(elev) > np.min(elev):
        hillshade = ls.shade(elev, cmap=plt.cm.gist_earth, blend_mode="overlay", vert_exag=1.5)
        ax.imshow(hillshade, origin="upper")
    else:
        ax.imshow(elev, cmap="gray", origin="upper")

    # 2. Classified Arrival Time Bands
    # 0: Unburned, 1: 0-2h (0-120m), 2: 2-4h (120-240m), 3: 4-8h (240-480m), 4: 8-12h (480-720m)
    band_grid = np.zeros_like(arrival, dtype=int)
    band_grid[(arrival > 0.0) & (arrival <= 120.0)] = 1
    band_grid[(arrival > 120.0) & (arrival <= 240.0)] = 2
    band_grid[(arrival > 240.0) & (arrival <= 480.0)] = 3
    band_grid[(arrival > 480.0) & (arrival <= 720.0)] = 4

    band_colors = [
        (0.0, 0.0, 0.0, 0.0),    # 0: transparent (unburned)
        (0.84, 0.19, 0.15, 0.85), # 1: 0-2h (crimson red)
        (0.99, 0.55, 0.35, 0.80), # 2: 2-4h (vibrant orange)
        (1.00, 0.88, 0.55, 0.75), # 3: 4-8h (amber yellow)
        (0.57, 0.75, 0.86, 0.70), # 4: 8-12h (sky blue)
    ]
    cmap_bands = ListedColormap(band_colors)
    ax.imshow(band_grid, cmap=cmap_bands, vmin=0, vmax=4, origin="upper")

    # 3. Plot Ignition Points
    for r, c, _ in ignitions:
        ax.plot(c, r, marker="*", color="#ffff00", markersize=14, markeredgecolor="black", markeredgewidth=1.5, zorder=10)

    # 4. Wind Direction Arrow
    mean_speed = float(np.mean(wind.speed_ms[:12])) if wind.speed_ms else 0.0
    mean_dir_from = float(np.mean(wind.dir_from_deg[:12])) if wind.dir_from_deg else 0.0
    wind_to_deg = (mean_dir_from + 180.0) % 360.0

    # Convert bearing clockwise from North to polar dx, dy on screen (col right, row down)
    theta_rad = np.radians(wind_to_deg)
    # North is up (dy < 0), East is right (dx > 0)
    arrow_dx = np.sin(theta_rad)
    arrow_dy = -np.cos(theta_rad)

    # Inset wind indicator box
    arrow_len = 35.0
    box_x = grid.nx * 0.88
    box_y = grid.ny * 0.12

    ax.annotate(
        "",
        xy=(box_x + arrow_dx * arrow_len, box_y + arrow_dy * arrow_len),
        xytext=(box_x, box_y),
        arrowprops=dict(facecolor="#00ffff", edgecolor="black", width=2.5, headwidth=9, shrink=0.05),
        zorder=12,
    )
    ax.text(
        box_x,
        box_y + 18,
        f"Wind {mean_speed:.1f} m/s\nFrom {mean_dir_from:.0f}°",
        color="white",
        fontsize=9,
        fontweight="bold",
        ha="center",
        va="top",
        bbox=dict(boxstyle="round,pad=0.3", facecolor="black", alpha=0.6, edgecolor="none"),
        zorder=12,
    )

    # 5. Legend
    legend_handles = [
        mpatches.Patch(color=band_colors[1], label="0 - 2 hours"),
        mpatches.Patch(color=band_colors[2], label="2 - 4 hours"),
        mpatches.Patch(color=band_colors[3], label="4 - 8 hours"),
        mpatches.Patch(color=band_colors[4], label="8 - 12 hours"),
        plt.Line2D([0], [0], marker="*", color="w", markerfacecolor="#ffff00", markeredgecolor="black", markersize=12, label="Ignition"),
    ]
    ax.legend(handles=legend_handles, loc="lower left", framealpha=0.85, facecolor="#1a1a1a", labelcolor="white", title="Isochrones", title_fontsize=10)

    # Title & Labels
    ax.set_title(
        f"EmberRoute Fire Arrival Isochrones (12h Horizon)\n"
        f"Burned Area: 2h={sim_stats['area_ha_2h']:.0f}ha | 6h={sim_stats['area_ha_6h']:.0f}ha | 12h={sim_stats['area_ha_12h']:.0f}ha | Reach={sim_stats['max_downwind_extent_km']:.1f}km",
        fontsize=11,
        pad=10,
    )
    ax.set_xlabel("Grid Column (East ->)")
    ax.set_ylabel("Grid Row (South ->)")

    fig.tight_layout()
    fig.savefig(output_path)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description="Render wildfire spread simulation over terrain.")
    parser.add_argument("--west", type=float, default=-120.2, help="West longitude (deg)")
    parser.add_argument("--south", type=float, default=38.1, help="South latitude (deg)")
    parser.add_argument("--east", type=float, default=-120.0, help="East longitude (deg)")
    parser.add_argument("--north", type=float, default=38.3, help="North latitude (deg)")
    parser.add_argument("--ign-lat", type=float, default=None, help="Scenario ignition latitude")
    parser.add_argument("--ign-lon", type=float, default=None, help="Scenario ignition longitude")
    parser.add_argument("--res-m", type=float, default=None, help="Grid resolution in metres")
    parser.add_argument("--horizon-min", type=int, default=720, help="Simulation horizon (minutes)")
    parser.add_argument("--output", type=str, default=".cache/debug/spread_simulation.png", help="Output PNG path")
    args = parser.parse_args()

    aoi = AOI(west=args.west, south=args.south, east=args.east, north=args.north)

    print("=" * 75)
    print("                 EMBERROUTE WILDFIRE SPREAD SIMULATION                 ")
    print("=" * 75)
    print(f"AOI: [{aoi.west:.4f}, {aoi.south:.4f}, {aoi.east:.4f}, {aoi.north:.4f}]")
    print(f"Center: ({aoi.center[0]:.4f}, {aoi.center[1]:.4f}) | Extent: {aoi.width_km:.1f} km x {aoi.height_km:.1f} km")

    # 1. Ingest layers
    t0 = time.time()
    layers, prov_layers, layer_warnings = build_layers(aoi, res_m=args.res_m)
    print(f"Static Layers Ingested : {time.time() - t0:.2f}s | Grid: {layers.grid.nx}x{layers.grid.ny} ({layers.grid.res_m:.1f}m res)")

    # 2. Ingest live weather
    wind, prov_wind = fetch_wind_series(lat=aoi.center[0], lon=aoi.center[1], hours_ahead=24)
    mean_wind_spd = float(np.mean(wind.speed_ms[:12]))
    mean_wind_dir = float(np.mean(wind.dir_from_deg[:12]))
    print(f"Live Weather Ingested  : Wind {mean_wind_spd:.1f} m/s from {mean_wind_dir:.0f}° | RH: {wind.rh[0]:.0f}%")

    # 3. Determine ignitions
    if args.ign_lat is not None and args.ign_lon is not None:
        ignitions = ignition_from_point(layers, args.ign_lat, args.ign_lon)
        print(f"Ignition Source        : Scenario point ({args.ign_lat:.4f}, {args.ign_lon:.4f})")
    else:
        # Check live FIRMS detections
        try:
            dets, prov_firms = fetch_detections(aoi=aoi, hours=24)
            if dets:
                ignitions = ignitions_from_detections(layers, dets)
                print(f"Ignition Source        : {len(ignitions)} cells from NASA FIRMS active detections")
            else:
                raise ValueError("No active FIRMS detections in AOI")
        except Exception:
            # Fallback to center of AOI
            center_lat, center_lon = aoi.center
            ignitions = ignition_from_point(layers, center_lat, center_lon)
            print(f"Ignition Source        : Domain centroid ({center_lat:.4f}, {center_lon:.4f})")

    # 4. Run anisotropic minimum travel-time simulation
    params = SpreadParams(horizon_min=args.horizon_min)
    t_sim = time.time()
    result = simulate_spread(layers, wind, ignitions, params)
    sim_duration = time.time() - t_sim

    # 5. Compute summary statistics
    sim_stats = stats(result)

    print("-" * 75)
    print(f"Simulation Runtime     : {sim_duration:.3f} seconds (internal: {result.runtime_s:.3f}s)")
    print(f"Grid Size              : {layers.grid.nx} columns x {layers.grid.ny} rows ({layers.grid.nx * layers.grid.ny} cells)")
    print(f"Resolution             : {layers.grid.res_m:.1f} metres")
    print(f"Burned Area Stats (ha) : 2h = {sim_stats['area_ha_2h']} ha | 6h = {sim_stats['area_ha_6h']} ha | 12h = {sim_stats['area_ha_12h']} ha")
    print(f"Max Downwind Reach     : {sim_stats['max_downwind_extent_km']} km")
    print(f"Displacement Bearing   : {sim_stats['centroid_displacement_bearing_deg']}° clockwise from North")
    print(f"Stats Dict             : {sim_stats}")

    # 6. Render visual map
    out_file = Path(args.output)
    render_spread_map(layers, result, wind, ignitions, sim_stats, out_file)
    print(f"\nSaved Spread Map       : {out_file.resolve()}")
    print("=" * 75)


if __name__ == "__main__":
    main()
