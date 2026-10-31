"""Unit tests for geospatial mathematics, grid generation, and projections."""

import numpy as np
import pytest
from core.geo import bearing_deg, cell_centers_lonlat, haversine_m, lonlat_to_rc, make_grid, rc_to_lonlat, utm_epsg_for
from core.models import AOI


def test_aoi_validation_errors() -> None:
    """Test that AOI enforces bounds order and maximum 0.6 degree extent."""
    # Valid AOI
    aoi = AOI(west=-120.2, south=38.1, east=-120.0, north=38.3)
    assert aoi.center == (38.2, -120.1)
    assert aoi.width_km > 0
    assert aoi.height_km > 0

    # Invalid: west >= east
    with pytest.raises(ValueError, match="west .* strictly less than east"):
        AOI(west=-120.0, south=38.1, east=-120.2, north=38.3)

    # Invalid: south >= north
    with pytest.raises(ValueError, match="south .* strictly less than north"):
        AOI(west=-120.2, south=38.4, east=-120.0, north=38.3)

    # Invalid: width > 0.6 degrees
    with pytest.raises(ValueError, match="AOI width .* exceeds maximum"):
        AOI(west=-121.0, south=38.1, east=-120.3, north=38.3)

    # Invalid: height > 0.6 degrees
    with pytest.raises(ValueError, match="AOI height .* exceeds maximum"):
        AOI(west=-120.2, south=37.5, east=-120.0, north=38.2)


def test_bearing_deg_eight_directions() -> None:
    """Test bearing_deg for all 8 cardinal and intercardinal compass directions."""
    # North: dr < 0, dc == 0
    assert bearing_deg(-1, 0) == pytest.approx(0.0)
    # North-East: dr < 0, dc > 0
    assert bearing_deg(-1, 1) == pytest.approx(45.0)
    # East: dr == 0, dc > 0
    assert bearing_deg(0, 1) == pytest.approx(90.0)
    # South-East: dr > 0, dc > 0
    assert bearing_deg(1, 1) == pytest.approx(135.0)
    # South: dr > 0, dc == 0
    assert bearing_deg(1, 0) == pytest.approx(180.0)
    # South-West: dr > 0, dc < 0
    assert bearing_deg(1, -1) == pytest.approx(225.0)
    # West: dr == 0, dc < 0
    assert bearing_deg(0, -1) == pytest.approx(270.0)
    # North-West: dr < 0, dc < 0
    assert bearing_deg(-1, -1) == pytest.approx(315.0)


def test_make_grid_never_exceeds_max_cells() -> None:
    """Test that make_grid coarsens resolution to respect max_cells."""
    aoi = AOI(west=-120.5, south=38.0, east=-120.0, north=38.5)

    for max_cells in [100, 250, 400, 1000]:
        grid = make_grid(aoi, res_m=30.0, max_cells=max_cells)
        total_cells = grid.nx * grid.ny
        assert total_cells <= max_cells, f"Expected total_cells <= {max_cells}, got {total_cells}"
        assert grid.nx > 0
        assert grid.ny > 0
        assert grid.res_m >= 30.0


def test_lonlat_rc_roundtrip() -> None:
    """Test round-trip conversion between (row, col) and (lon, lat) with error under half a cell."""
    aoi = AOI(west=-120.3, south=38.2, east=-120.1, north=38.4)
    grid = make_grid(aoi, res_m=90.0, max_cells=400)

    # Test single scalar points
    test_rows = [0, 5, grid.ny - 1]
    test_cols = [0, 4, grid.nx - 1]

    for r_in in test_rows:
        for c_in in test_cols:
            lon, lat = rc_to_lonlat(grid, r_in, c_in)
            r_out, c_out = lonlat_to_rc(grid, lon, lat)

            assert abs(r_out - r_in) < 0.5, f"Row error {abs(r_out - r_in)} exceeds half a cell"
            assert abs(c_out - c_in) < 0.5, f"Col error {abs(c_out - c_in)} exceeds half a cell"

    # Test vectorized array round-trip
    r_arr = np.array([1, 2, 3])
    c_arr = np.array([4, 5, 6])
    lons, lats = rc_to_lonlat(grid, r_arr, c_arr)
    r_rec, c_rec = lonlat_to_rc(grid, lons, lats)

    assert np.all(np.abs(r_rec - r_arr) < 0.5)
    assert np.all(np.abs(c_rec - c_arr) < 0.5)


def test_utm_epsg_for() -> None:
    """Test UTM zone determination."""
    # Northern hemisphere (California: San Francisco / Bay Area in UTM 10N)
    assert utm_epsg_for(37.77, -122.42) == 32610
    # Southern hemisphere (Sydney, Australia in UTM 56S)
    assert utm_epsg_for(-33.86, 151.2) == 32756


def test_haversine_m() -> None:
    """Test haversine distance calculation."""
    # Distance between same points is 0
    assert haversine_m(0.0, 0.0, 0.0, 0.0) == 0.0
    # 1 degree latitude is approximately 111,195 metres
    d = haversine_m(0.0, 0.0, 0.0, 1.0)
    assert 110_000 < d < 112_000
