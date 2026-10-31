"""Prefetch and render static layers (elevation with hillshade and fuel classes) for an AOI.

CLI usage:
    python scripts/prefetch.py --west -120.2 --south 38.1 --east -120.0 --north 38.3 [--res-m 90]
"""

import argparse
from pathlib import Path
import sys
import time

# Ensure repository root is on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import matplotlib.pyplot as plt
from matplotlib.colors import BoundaryNorm, ListedColormap
from matplotlib.colors import LightSource
import numpy as np

from core.fire.fuel import CLASS_NAMES
from core.layers import build_layers
from core.models import AOI


def save_debug_visualizations(elevation: np.ndarray, fuel_class: np.ndarray, output_dir: Path) -> None:
    """Save debug visual verification PNGs for elevation hillshade and fuel classes."""
    output_dir.mkdir(parents=True, exist_ok=True)

    # 1. Elevation with hillshade
    elev_path = output_dir / "elevation_hillshade.png"
    fig, ax = plt.subplots(figsize=(8, 7), dpi=150)
    ls = LightSource(azdeg=315, altdeg=45)
    norm = plt.Normalize(vmin=float(np.min(elevation)), vmax=float(np.max(elevation)))

    if np.max(elevation) > np.min(elevation):
        rgb_hillshade = ls.shade(elevation, cmap=plt.cm.terrain, blend_mode="overlay")
        ax.imshow(rgb_hillshade)
    else:
        ax.imshow(elevation, cmap="terrain")

    sm = plt.cm.ScalarMappable(cmap=plt.cm.terrain, norm=norm)
    sm.set_array([])
    fig.colorbar(sm, ax=ax, label="Elevation (m)")
    ax.set_title("Elevation with 315° Hillshade")
    fig.tight_layout()
    fig.savefig(elev_path)
    plt.close(fig)

    # 2. Fuel classification map
    fuel_path = output_dir / "fuel_classes.png"
    fig, ax = plt.subplots(figsize=(9, 7), dpi=150)

    # Map discrete fuel class values to standard color palette
    palette = {
        10: "#006400",  # tree cover (dark green)
        20: "#ffbb22",  # shrubland (yellow-orange)
        30: "#ffff4c",  # grassland (yellow)
        40: "#f096ff",  # cropland (pink)
        50: "#fa0000",  # built-up (red)
        60: "#b4b4b4",  # bare (gray)
        70: "#f0f0f0",  # snow (white)
        80: "#0064c8",  # water (blue)
        90: "#0096a0",  # wetland (teal)
        95: "#00cf75",  # mangroves (light green)
        100: "#fae6a0",  # moss
    }

    unique_vals = sorted(np.unique(fuel_class))
    colors = [palette.get(int(v), "#808080") for v in unique_vals]
    cmap = ListedColormap(colors)
    bounds = list(range(len(unique_vals) + 1))
    norm_bounds = BoundaryNorm(bounds, cmap.N)

    # Remap values to [0..len(unique_vals)-1] for display
    display_grid = np.zeros_like(fuel_class, dtype=int)
    for idx, v in enumerate(unique_vals):
        display_grid[fuel_class == v] = idx

    im = ax.imshow(display_grid, cmap=cmap, norm=norm_bounds)
    cbar = fig.colorbar(im, ax=ax, ticks=[i + 0.5 for i in range(len(unique_vals))])
    cbar.ax.set_yticklabels([f"{v}: {CLASS_NAMES.get(int(v), 'unknown')}" for v in unique_vals])
    ax.set_title("ESA WorldCover Fuel Classes")
    fig.tight_layout()
    fig.savefig(fuel_path)
    plt.close(fig)

    print(f"\n[Artifacts] Debug visual layers saved:")
    print(f"  - Elevation: {elev_path}")
    print(f"  - Land cover: {fuel_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Prefetch terrain and fuel layers for an AOI.")
    parser.add_argument("--west", type=float, required=True, help="West longitude (deg)")
    parser.add_argument("--south", type=float, required=True, help="South latitude (deg)")
    parser.add_argument("--east", type=float, required=True, help="East longitude (deg)")
    parser.add_argument("--north", type=float, required=True, help="North latitude (deg)")
    parser.add_argument("--res-m", type=float, default=None, help="Optional grid resolution in metres")
    args = parser.parse_args()

    aoi = AOI(west=args.west, south=args.south, east=args.east, north=args.north)

    print("=" * 70)
    print("                     EMBERROUTE LAYER PREFETCH                     ")
    print("=" * 70)
    print(f"AOI: [{aoi.west:.4f}, {aoi.south:.4f}, {aoi.east:.4f}, {aoi.north:.4f}]")
    print(f"Center: ({aoi.center[0]:.4f}, {aoi.center[1]:.4f}) | Extent: {aoi.width_km:.1f} km x {aoi.height_km:.1f} km")

    t0 = time.time()
    layers, provenance_list, warnings = build_layers(aoi, res_m=args.res_m)
    elapsed_s = time.time() - t0

    grid = layers.grid
    elev = layers.elevation
    fuel = layers.fuel_class

    print("-" * 70)
    print(f"Execution Time : {elapsed_s:.2f} seconds")
    print(f"Grid Spec      : {grid.nx} cols x {grid.ny} rows ({grid.nx * grid.ny} cells)")
    print(f"Resolution     : {grid.res_m:.1f} metres (UTM EPSG:{grid.epsg})")
    print(f"Elevation Min  : {float(np.min(elev)):.1f} m")
    print(f"Elevation Max  : {float(np.max(elev)):.1f} m")
    print(f"Elevation Mean : {float(np.mean(elev)):.1f} m")

    print("\nFuel Class Histogram:")
    unique_classes, counts = np.unique(fuel, return_counts=True)
    total_cells = grid.nx * grid.ny
    for code, count in zip(unique_classes, counts):
        name = CLASS_NAMES.get(int(code), f"unknown ({code})")
        pct = (count / total_cells) * 100.0
        print(f"  Class {code:<3} ({name:<12}): {count:>5} cells ({pct:>5.1f}%)")

    print("\nData Provenance:")
    for prov in provenance_list:
        stale_flag = " [STALE]" if prov.is_stale else " [FRESH]"
        print(f"  - {prov.source:<15}: {prov.name} ({prov.ttl_s}s TTL){stale_flag}")

    if warnings:
        print("\nWarnings:")
        for w in warnings:
            print(f"  ! {w}")

    # Check if road network (osm.py) is available
    try:
        from core.data import osm
        if hasattr(osm, "get_road_graph"):
            print("\nFetching road graph via core.data.osm...")
            # road graph fetch hook
    except (ImportError, AttributeError):
        pass

    # Save visual debug plots into .cache/debug/
    debug_dir = Path(".cache") / "debug"
    save_debug_visualizations(elev, fuel, debug_dir)
    print("=" * 70)


if __name__ == "__main__":
    main()
