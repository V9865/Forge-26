"""Acceptance verification script for OpenStreetMap road network, settlements, and shelters.

Fetches data for a 0.2 x 0.2 degree area, reports metrics and timings,
renders a debug PNG map with matplotlib, and runs a second time to demonstrate
disk caching performance.
"""

from pathlib import Path
import sys
import time

# Ensure workspace root is in sys.path
WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

import matplotlib.pyplot as plt
import networkx as nx

from core.data.osm import get_road_graph, get_settlements, get_shelters
from core.models import AOI


def run_osm_verification() -> None:
    # 0.2 x 0.2 degree area around Grass Valley & Nevada City, CA (foothill forest & village zone)
    aoi = AOI(west=-121.10, south=39.15, east=-120.90, north=39.35)
    debug_dir = Path(".cache") / "debug"
    debug_dir.mkdir(parents=True, exist_ok=True)
    debug_png_path = debug_dir / "osm_road_graph_debug.png"

    print("=" * 65)
    print("RUN 1: Live Fetch / Initial Load (Download & Process)")
    print(f"AOI: West={aoi.west}, South={aoi.south}, East={aoi.east}, North={aoi.north}")
    print("=" * 65)

    start_time = time.perf_counter()
    G = get_road_graph(aoi)
    graph_time = time.perf_counter() - start_time

    settlements_start = time.perf_counter()
    settlements = get_settlements(aoi, G)
    settlements_time = time.perf_counter() - settlements_start

    shelters_start = time.perf_counter()
    shelters = get_shelters(aoi)
    shelters_time = time.perf_counter() - shelters_start

    total_first_run_time = time.perf_counter() - start_time

    print(f"Graph nodes:       {len(G.nodes)}")
    print(f"Graph edges:       {len(G.edges)}")
    print(f"Settlements:       {len(settlements)}")
    print(f"Shelters:          {len(shelters)}")
    print(f"Road graph time:   {graph_time:.2f} s")
    print(f"Settlements time:  {settlements_time:.2f} s")
    print(f"Shelters time:     {shelters_time:.2f} s")
    print(f"Total Run 1 time:  {total_first_run_time:.2f} s")

    # Sample edge attributes
    if len(G.edges) > 0:
        sample_edge = next(iter(G.edges(data=True)))
        print(f"Sample edge attrs: speed_kph={sample_edge[2].get('speed_kph')} km/h, "
              f"travel_time={sample_edge[2].get('travel_time'):.1f} s, "
              f"highway={sample_edge[2].get('highway')}")

    # Print top 5 settlements
    print("\nSample settlements:")
    for s in settlements[:5]:
        print(f" - {s.name} (lat={s.lat:.4f}, lon={s.lon:.4f}, snapped_node={s.node})")

    # Print top 5 shelters
    print("\nSample shelters:")
    for name, lat, lon, kind in shelters[:5]:
        print(f" - [{kind.upper()}] {name} ({lat:.4f}, {lon:.4f})")

    # Render debug PNG
    print(f"\nRendering debug plot to {debug_png_path}...")
    fig, ax = plt.subplots(figsize=(10, 10), dpi=150)

    # Plot road edges
    for u, v, data in G.edges(data=True):
        u_node = G.nodes[u]
        v_node = G.nodes[v]
        ax.plot([u_node["x"], v_node["x"]], [u_node["y"], v_node["y"]],
                color="#64748b", linewidth=0.6, alpha=0.7, zorder=1)

    # Plot settlements
    if settlements:
        s_lons = [s.lon for s in settlements]
        s_lats = [s.lat for s in settlements]
        ax.scatter(s_lons, s_lats, color="#dc2626", s=35, marker="o", edgecolors="black",
                   linewidths=0.5, label=f"Settlements ({len(settlements)})", zorder=3)
        for s in settlements[:8]:
            ax.annotate(s.name, (s.lon, s.lat), fontsize=7, color="#7f1d1d",
                        xytext=(3, 3), textcoords="offset points", fontweight="bold")

    # Plot shelters
    if shelters:
        sh_lons = [sh[2] for sh in shelters]
        sh_lats = [sh[1] for sh in shelters]
        ax.scatter(sh_lons, sh_lats, color="#2563eb", s=25, marker="^", edgecolors="black",
                   linewidths=0.5, label=f"Shelters ({len(shelters)})", zorder=2)

    ax.set_title(f"EmberRoute Road Network & Assets\nAOI: [{aoi.west}, {aoi.south}, {aoi.east}, {aoi.north}]", fontsize=11)
    ax.set_xlabel("Longitude (deg)")
    ax.set_ylabel("Latitude (deg)")
    ax.legend(loc="upper right", fontsize=8)
    ax.grid(True, linestyle="--", alpha=0.3)
    plt.tight_layout()
    plt.savefig(debug_png_path)
    plt.close()
    print(f"Debug PNG saved successfully ({debug_png_path.stat().st_size / 1024:.1f} KB)")

    print("\n" + "=" * 65)
    print("RUN 2: Disk Cache Benchmark (GraphML Reload)")
    print("=" * 65)
    start_time_cache = time.perf_counter()
    cached_G = get_road_graph(aoi)
    total_cache_time = time.perf_counter() - start_time_cache

    print(f"Cached graph nodes: {len(cached_G.nodes)}")
    print(f"Cached graph edges: {len(cached_G.edges)}")
    print(f"Run 2 reload time:  {total_cache_time:.4f} s")
    speedup = total_first_run_time / max(total_cache_time, 1e-6)
    print(f"Cache speedup:      {speedup:.1f}x faster")
    print("=" * 65)


if __name__ == "__main__":
    run_osm_verification()
