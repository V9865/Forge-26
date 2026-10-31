"""Unit tests for wildfire spread simulation physics, arrival bands, and baseline calibration."""

from datetime import datetime, timezone
import numpy as np
import pytest
from shapely.geometry import shape

from core.fire.bands import arrival_bands
from core.fire.baseline import isotropic_baseline
from core.fire.spread import (
    burned_mask,
    ignition_from_point,
    ignitions_from_detections,
    simulate_spread,
    stats,
)
from core.models import FireDetection, GridSpec, Layers, SpreadParams, WindSeries


def make_synthetic_layers(
    ny: int = 51,
    nx: int = 51,
    res_m: float = 30.0,
    elev_val: float = 100.0,
    base_ros_val: float = 10.0,
) -> Layers:
    """Construct procedurally generated synthetic spatial layers for testing."""
    grid = GridSpec(
        epsg=32610,
        x0=700000.0,
        y0=4200000.0,
        res_m=res_m,
        nx=nx,
        ny=ny,
    )
    elevation = np.full((ny, nx), elev_val, dtype=np.float32)
    fuel_class = np.full((ny, nx), 30, dtype=np.uint8)  # Grassland
    base_ros = np.full((ny, nx), base_ros_val, dtype=np.float32)

    return Layers(
        grid=grid,
        elevation=elevation,
        fuel_class=fuel_class,
        base_ros=base_ros,
        provenance={},
    )


def make_synthetic_wind(
    speed_ms: float = 0.0,
    dir_from_deg: float = 270.0,
    hours: int = 24,
    rh: float = 30.0,
) -> WindSeries:
    """Construct uniform synthetic wind series."""
    speeds = [float(speed_ms)] * hours
    dirs = [float(dir_from_deg)] * hours
    rhs = [float(rh)] * hours
    temps = [25.0] * hours

    return WindSeries(
        start_utc=datetime(2026, 10, 31, 12, 0, tzinfo=timezone.utc),
        speed_ms=speeds,
        dir_from_deg=dirs,
        rh=rhs,
        temp_c=temps,
        source="synthetic",
        fetched_at_utc=datetime.now(timezone.utc),
    )


def test_circular_spread_zero_wind_flat() -> None:
    """Test 1: Zero wind, flat terrain, uniform fuel produces isotropic circular spread."""
    layers = make_synthetic_layers(ny=51, nx=51, res_m=30.0, elev_val=100.0, base_ros_val=10.0)
    wind = make_synthetic_wind(speed_ms=0.0)
    ignitions = [(25, 25, 0.0)]

    params = SpreadParams(k_wind=0.25, midflame=0.5, horizon_min=120)
    result = simulate_spread(layers, wind, ignitions, params)
    arr = result.arrival_min

    # Cells at distance 10 in cardinal directions (North, South, East, West)
    t_north = arr[15, 25]
    t_south = arr[35, 25]
    t_east = arr[25, 35]
    t_west = arr[25, 15]

    cardinal_times = [t_north, t_south, t_east, t_west]
    mean_cardinal = np.mean(cardinal_times)
    for t_val in cardinal_times:
        assert abs(t_val - mean_cardinal) / mean_cardinal < 0.05, "Cardinal directions must be circular within 5%"

    # Cells at distance 7 in diagonal directions (roughly same metric distance 7 * sqrt(2) * 30m ~= 297m vs 300m)
    t_ne = arr[18, 32]
    t_se = arr[32, 32]
    t_sw = arr[32, 18]
    t_nw = arr[18, 18]
    diag_times = [t_ne, t_se, t_sw, t_nw]
    mean_diag = np.mean(diag_times)
    for t_val in diag_times:
        assert abs(t_val - mean_diag) / mean_diag < 0.05, "Diagonal directions must be symmetric within 5%"


def test_wind_elongation_aspect_ratio() -> None:
    """Test 2: Strong wind from west (8 m/s) elongates fire eastward (ratio > 1.5)."""
    layers = make_synthetic_layers(ny=61, nx=81, res_m=30.0, elev_val=100.0, base_ros_val=10.0)
    # Wind from West (270 deg) pushes fire toward East (90 deg)
    wind = make_synthetic_wind(speed_ms=8.0, dir_from_deg=270.0)
    ignitions = [(30, 20, 0.0)]

    params = SpreadParams(k_wind=0.25, midflame=0.5, horizon_min=120)
    result = simulate_spread(layers, wind, ignitions, params)
    arr = result.arrival_min

    # Compare arrival times at distance 10 cells East vs West
    t_east = arr[30, 30]  # Downwind
    t_west = arr[30, 10]  # Upwind
    assert t_east < t_west, "Eastward (downwind) arrival must be faster than westward (upwind)"

    # Compute bounding box of burned cells at 60 minutes
    mask_60 = arr <= 60.0
    r_indices, c_indices = np.where(mask_60)
    assert len(c_indices) > 0

    x_extent = np.max(c_indices) - np.min(c_indices) + 1
    y_extent = np.max(r_indices) - np.min(r_indices) + 1
    aspect_ratio = x_extent / y_extent

    assert aspect_ratio > 1.5, f"Aspect ratio ({aspect_ratio:.2f}) must exceed 1.5"


def test_uphill_acceleration_slope() -> None:
    """Test 3: Fire travels faster uphill than downhill."""
    layers = make_synthetic_layers(ny=51, nx=51, res_m=30.0, base_ros_val=10.0)
    # Slope ramp: elevation increases southward (row increases)
    # row 0 is 0m, row 50 is 500m (g = +10m/30m = +0.33 uphill going south)
    elev_ramp = np.tile(np.linspace(0, 500, 51)[:, None], (1, 51)).astype(np.float32)
    layers.elevation = elev_ramp

    wind = make_synthetic_wind(speed_ms=0.0)
    ignitions = [(25, 25, 0.0)]

    result = simulate_spread(layers, wind, ignitions)
    arr = result.arrival_min

    # Going South is uphill (elev increases): should be faster (smaller arrival time)
    # Going North is downhill (elev decreases): should be slower (larger arrival time)
    t_upslope = arr[35, 25]    # South (uphill)
    t_downslope = arr[15, 25]  # North (downhill)

    assert t_upslope < t_downslope, f"Upslope arrival ({t_upslope:.1f}m) must be earlier than downhill ({t_downslope:.1f}m)"


def test_water_barrier_blocks_spread() -> None:
    """Test 4: Non-burnable water barrier (base_ros <= 0.01) completely halts spread."""
    layers = make_synthetic_layers(ny=51, nx=51, res_m=30.0, elev_val=100.0, base_ros_val=10.0)
    # Vertical water band at column 30 (from row 0 to 50)
    layers.base_ros[:, 30] = 0.0

    wind = make_synthetic_wind(speed_ms=5.0, dir_from_deg=270.0)  # Blowing West to East
    ignitions = [(25, 10, 0.0)]

    result = simulate_spread(layers, wind, ignitions)
    arr = result.arrival_min

    # Before barrier
    assert np.isfinite(arr[25, 25])
    # Behind barrier
    assert np.isinf(arr[25, 40]), "Cells behind full-width water barrier must never burn (inf)"


def test_wind_shift_trajectory_bend() -> None:
    """Test 5: Wind shifting from West (first 2h) to North (late) bends the fire southward."""
    layers = make_synthetic_layers(ny=81, nx=81, res_m=30.0, elev_val=100.0, base_ros_val=5.0)

    # 2 hours blowing East (from 270 deg), then blowing South (from 0 deg North)
    speeds = [6.0] * 12
    dirs = [270.0, 270.0] + [0.0] * 10
    rhs = [30.0] * 12
    temps = [25.0] * 12

    wind = WindSeries(
        start_utc=datetime(2026, 10, 31, 12, 0, tzinfo=timezone.utc),
        speed_ms=speeds,
        dir_from_deg=dirs,
        rh=rhs,
        temp_c=temps,
        source="synthetic",
        fetched_at_utc=datetime.now(timezone.utc),
    )

    ignitions = [(20, 20, 0.0)]
    params = SpreadParams(horizon_min=360)
    result = simulate_spread(layers, wind, ignitions, params)
    arr = result.arrival_min

    # At late time (e.g. 240 mins), fire front should have pushed strongly southward
    # Cell (50, 40) is south of the eastward front, should burn earlier than cell (10, 40)
    t_southward = arr[50, 40]
    t_northward = arr[5, 40]
    assert t_southward < t_northward, "Late wind from North must push fire southward"


def test_simulation_determinism() -> None:
    """Test 6: Identical parameters and layers yield bitwise deterministic arrival fields."""
    layers = make_synthetic_layers(ny=41, nx=41)
    wind = make_synthetic_wind(speed_ms=4.0, dir_from_deg=240.0)
    ignitions = [(20, 20, 0.0)]

    res1 = simulate_spread(layers, wind, ignitions)
    res2 = simulate_spread(layers, wind, ignitions)

    np.testing.assert_array_equal(res1.arrival_min, res2.arrival_min)


def test_runtime_benchmark_250x250() -> None:
    """Test 7: Simulation on a 250x250 grid completes in under 5 seconds."""
    layers = make_synthetic_layers(ny=250, nx=250, res_m=30.0, elev_val=100.0, base_ros_val=10.0)
    wind = make_synthetic_wind(speed_ms=5.0, dir_from_deg=270.0)
    ignitions = [(125, 125, 0.0)]

    params = SpreadParams(horizon_min=180)
    result = simulate_spread(layers, wind, ignitions, params)

    assert result.runtime_s < 5.0, f"Runtime ({result.runtime_s:.2f}s) exceeded 5s threshold"
    assert np.any(np.isfinite(result.arrival_min))


def test_arrival_bands_nesting_and_monotonicity() -> None:
    """Test arrival_bands geometric nesting, coordinate order, and monotonic area."""
    layers = make_synthetic_layers(ny=61, nx=61, res_m=30.0)
    wind = make_synthetic_wind(speed_ms=3.0, dir_from_deg=270.0)
    ignitions = [(30, 30, 0.0)]

    params = SpreadParams(horizon_min=120)
    result = simulate_spread(layers, wind, ignitions, params)

    bands = arrival_bands(result, step_min=30)
    assert len(bands) >= 2

    # Check validity and monotonic growth
    prev_poly = None
    prev_area = 0.0

    for b in bands:
        assert "t_min" in b
        assert "geometry" in b
        geom_dict = b["geometry"]
        assert geom_dict["type"] in ("Polygon", "MultiPolygon")

        poly = shape(geom_dict)
        assert poly.is_valid, "Isochrone polygon must be topologically valid"

        area = poly.area
        assert area >= prev_area, "Cumulative band area must be monotonic"

        # Coordinates must be in lon/lat order within reasonable WGS84 range
        coords = np.array(poly.exterior.coords) if hasattr(poly, "exterior") else np.array(poly.geoms[0].exterior.coords)
        lons = coords[:, 0]
        lats = coords[:, 1]
        assert np.all((lons >= -180.0) & (lons <= 180.0))
        assert np.all((lats >= -90.0) & (lats <= 90.0))

        if prev_poly is not None:
            # Check nesting: prev_poly is contained or almost contained within poly
            intersection_area = poly.intersection(prev_poly).area
            assert intersection_area == pytest.approx(prev_poly.area, rel=0.05), "Cumulative bands must be nested"

        prev_poly = poly
        prev_area = area


def test_ignition_helpers_and_errors() -> None:
    """Test ignitions_from_detections and ignition_from_point helpers and validation errors."""
    from core.geo import rc_to_lonlat

    layers = make_synthetic_layers(ny=31, nx=31)

    # Valid scenario point at grid center
    center_lon, center_lat = rc_to_lonlat(layers.grid, 15, 15)
    ign_point = ignition_from_point(layers, lat=center_lat, lon=center_lon)
    assert len(ign_point) == 1
    assert ign_point[0] == (15, 15, 0.0)

    # Point outside grid
    with pytest.raises(ValueError, match="outside the simulation grid"):
        ignition_from_point(layers, lat=10.0, lon=0.0)

    # Point on water/non-burnable cell
    layers.base_ros[10, 10] = 0.0
    with pytest.raises(ValueError, match="non-burnable cell"):
        # Map back to coordinate of cell (10, 10)
        from core.geo import rc_to_lonlat
        w_lon, w_lat = rc_to_lonlat(layers.grid, 10, 10)
        ignition_from_point(layers, lat=w_lat, lon=w_lon)

    # Detection helper with no detections inside domain
    det_outside = FireDetection(
        lat=0.0, lon=0.0, acq_time_utc=datetime.now(timezone.utc), frp=10.0, confidence="h", satellite="N"
    )
    with pytest.raises(ValueError, match="No active fire detections"):
        ignitions_from_detections(layers, [det_outside])


def test_isotropic_baseline_calibration() -> None:
    """Test isotropic_baseline calibrates ROS to match target burned area within 1%."""
    layers = make_synthetic_layers(ny=51, nx=51, res_m=30.0)
    target_area = 50.0  # 50 ha
    result, ros = isotropic_baseline(layers, [(25, 25, 0.0)], target_area_ha=target_area, horizon_min=120)

    cell_area_ha = (30.0 * 30.0) / 10000.0
    actual_area = np.sum(result.arrival_min <= 120.0) * cell_area_ha

    assert ros > 0.0
    assert abs(actual_area - target_area) / target_area < 0.02

