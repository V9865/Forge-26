"""Unit tests for ESA WorldCover tile ID naming and fuel rate-of-spread mapping."""

import numpy as np
import pytest

from core.data.landcover import worldcover_tile_id
from core.fire.fuel import BASE_ROS_M_PER_MIN, CLASS_NAMES, base_ros


def test_worldcover_tile_id_four_hemispheres() -> None:
    """Test WorldCover tile ID calculation for four geographic quadrants."""
    # 1. North-East quadrant (Europe / Asia: e.g. Greece / Italy)
    # lat=38.2 -> floor(38.2/3)*3 = 36 -> N36
    # lon=12.5 -> floor(12.5/3)*3 = 12 -> E012
    assert worldcover_tile_id(lat=38.2, lon=12.5) == "N36E012"

    # 2. North-West quadrant (North America: e.g. California)
    # lat=38.2 -> floor(38.2/3)*3 = 36 -> N36
    # lon=-120.1 -> floor(-120.1/3)*3 = -41*3 = -123 -> W123
    assert worldcover_tile_id(lat=38.2, lon=-120.1) == "N36W123"

    # Exact boundary coordinate: lon=-120.0 -> floor(-120/3)*3 = -120 -> W120
    assert worldcover_tile_id(lat=38.0, lon=-120.0) == "N36W120"

    # 3. South-East quadrant (Australia: e.g. Sydney)
    # lat=-33.8 -> floor(-33.8/3)*3 = -12*3 = -36 -> S36
    # lon=151.2 -> floor(151.2/3)*3 = 50*3 = 150 -> E150
    assert worldcover_tile_id(lat=-33.8, lon=151.2) == "S36E150"

    # 4. South-West quadrant (South America: e.g. Brazil)
    # lat=-15.5 -> floor(-15.5/3)*3 = -6*3 = -18 -> S18
    # lon=-45.2 -> floor(-45.2/3)*3 = -16*3 = -48 -> W048
    assert worldcover_tile_id(lat=-15.5, lon=-45.2) == "S18W048"


def test_base_ros_fuel_mapping() -> None:
    """Test base rate-of-spread mapping against specified standard values."""
    # Build synthetic class array covering key landcover types
    classes = np.array([
        [10, 20, 30],
        [50, 80, 255],  # 255 is an unknown code
    ], dtype=np.uint8)

    ros = base_ros(classes)

    assert ros.shape == (2, 3)
    assert ros.dtype == np.float32

    # 10: tree cover -> 3.0 m/min
    assert ros[0, 0] == pytest.approx(3.0)
    # 20: shrubland -> 8.0 m/min
    assert ros[0, 1] == pytest.approx(8.0)
    # 30: grassland -> 15.0 m/min
    assert ros[0, 2] == pytest.approx(15.0)
    # 50: built-up -> 0.5 m/min
    assert ros[1, 0] == pytest.approx(0.5)
    # 80: water -> 0.0 m/min (non-burnable)
    assert ros[1, 1] == pytest.approx(0.0)
    # Unknown (255) -> fallback 3.0 m/min
    assert ros[1, 2] == pytest.approx(3.0)


def test_fuel_class_names_completeness() -> None:
    """Assert all defined base rate-of-spread codes possess human-readable names."""
    for code, speed in BASE_ROS_M_PER_MIN.items():
        assert code in CLASS_NAMES
        assert isinstance(CLASS_NAMES[code], str)
        assert speed >= 0.0
