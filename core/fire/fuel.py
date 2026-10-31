"""Fuel classification mapping and base rate-of-spread parameters for EmberRoute.

Maps ESA WorldCover land cover class codes to base rate-of-spread (m/min).
Note: These values are heuristic base model parameters calibrated for typical
fuel beds under zero-slope and zero-wind baseline conditions. They are subject
to further calibration and tuning during model validation.
"""

from typing import Dict
import numpy as np

CLASS_NAMES: Dict[int, str] = {
    10: "tree cover",
    20: "shrubland",
    30: "grassland",
    40: "cropland",
    50: "built-up",
    60: "bare",
    70: "snow",
    80: "water",
    90: "wetland",
    95: "mangroves",
    100: "moss",
}

BASE_ROS_M_PER_MIN: Dict[int, float] = {
    10: 3.0,
    20: 8.0,
    30: 15.0,
    40: 10.0,
    50: 0.5,
    60: 0.2,
    70: 0.0,
    80: 0.0,
    90: 1.0,
    95: 2.0,
    100: 2.0,
}

DEFAULT_BASE_ROS = 3.0  # Heuristic fallback for unknown or unclassified codes


def base_ros(fuel_class: np.ndarray) -> np.ndarray:
    """Compute base rate-of-spread in metres per minute from fuel class codes.

    Args:
        fuel_class: 2D numpy array of ESA WorldCover uint8 class codes.

    Returns:
        float32 numpy array of base rate-of-spread in m/min matching input shape.
        Unknown codes default to 3.0 m/min.
    """
    arr = np.asarray(fuel_class, dtype=np.int32)
    ros = np.full(arr.shape, DEFAULT_BASE_ROS, dtype=np.float32)

    for code, speed in BASE_ROS_M_PER_MIN.items():
        ros[arr == code] = speed

    return ros.astype(np.float32)
