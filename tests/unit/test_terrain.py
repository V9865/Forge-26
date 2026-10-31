"""Unit tests for terrain elevation decoding, slippy-map math, and slope gradient computation."""

import io
import numpy as np
from PIL import Image
import pytest

from core.data.terrain import compute_slope, decode_terrarium_png, lat_to_tile_y, lon_to_tile_x


def test_slippy_tile_math() -> None:
    """Test longitude and latitude conversion to slippy-map tile indices."""
    # Zoom level 0 has exactly 1 tile (0, 0)
    assert lon_to_tile_x(0.0, 0) == 0
    assert lat_to_tile_y(0.0, 0) == 0

    # Zoom level 1: 4 quadrants
    assert lon_to_tile_x(10.0, 1) == 1
    assert lon_to_tile_x(-10.0, 1) == 0
    assert lat_to_tile_y(10.0, 1) == 0
    assert lat_to_tile_y(-10.0, 1) == 1

    # Zoom level 12 California test coordinates
    assert lon_to_tile_x(-120.0, 12) == 682
    assert lat_to_tile_y(38.0, 12) == 1579


def test_decode_terrarium_png_procedural() -> None:
    """Test Terrarium elevation decoding formula against procedurally generated 2x2 RGB PNG."""
    # Create 2x2 RGB image with known encoded heights
    # Formula: elev = (R*256 + G + B/256) - 32768
    rgb_data = np.zeros((2, 2, 3), dtype=np.uint8)

    # Pixel (0, 0): R=128, G=0, B=0 -> (128*256 + 0 + 0) - 32768 = 0.0 m
    rgb_data[0, 0] = [128, 0, 0]

    # Pixel (0, 1): R=128, G=10, B=0 -> (128*256 + 10 + 0) - 32768 = 10.0 m
    rgb_data[0, 1] = [128, 10, 0]

    # Pixel (1, 0): R=130, G=10, B=128 -> (130*256 + 10 + 128/256) - 32768 = 522.5 m
    rgb_data[1, 0] = [130, 10, 128]

    # Pixel (1, 1): R=127, G=255, B=0 -> (127*256 + 255 + 0) - 32768 = -1.0 m
    rgb_data[1, 1] = [127, 255, 0]

    img = Image.fromarray(rgb_data, mode="RGB")
    buf = io.BytesIO()
    img.save(buf, format="PNG")

    decoded = decode_terrarium_png(buf.getvalue())

    assert decoded.shape == (2, 2)
    assert decoded[0, 0] == pytest.approx(0.0, abs=1e-3)
    assert decoded[0, 1] == pytest.approx(10.0, abs=1e-3)
    assert decoded[1, 0] == pytest.approx(522.5, abs=1e-3)
    assert decoded[1, 1] == pytest.approx(-1.0, abs=1e-3)


def test_slope_sign_convention_on_synthetic_ramp() -> None:
    """Test slope gradient sign convention: x points East, y points South."""
    # 1. Eastward elevation ramp: elevation increases left-to-right (col 0 to col 1)
    ramp_east = np.array([
        [100.0, 110.0],
        [100.0, 110.0],
    ], dtype=np.float32)

    res_m = 10.0
    dz_dx, dz_dy, slope = compute_slope(ramp_east, res_m=res_m)

    # dz_dx must be strictly positive (rising eastward)
    assert np.all(dz_dx > 0)
    # dz_dy must be zero (no north-south gradient)
    assert np.all(dz_dy == pytest.approx(0.0))
    # dz/dx = 1.0 -> slope angle is 45 degrees
    assert np.all(slope == pytest.approx(45.0, abs=1e-2))

    # 2. Southward elevation ramp: elevation increases top-to-bottom (row 0 to row 1)
    ramp_south = np.array([
        [100.0, 100.0],
        [110.0, 110.0],
    ], dtype=np.float32)

    dz_dx_s, dz_dy_s, slope_s = compute_slope(ramp_south, res_m=res_m)

    # dz_dy must be strictly positive (rising southward as row index increases)
    assert np.all(dz_dy_s > 0)
    assert np.all(dz_dx_s == pytest.approx(0.0))
    assert np.all(slope_s == pytest.approx(45.0, abs=1e-2))
