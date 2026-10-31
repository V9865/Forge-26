"""Spatial layers assembler for EmberRoute simulation domain.

Constructs simulation grid, extracts elevation and land cover layers,
computes baseline rate-of-spread, and compiles audit provenance records and warnings.
"""

import logging
from typing import List, Optional, Tuple
import numpy as np

from core.config import get_settings
from core.data.landcover import get_fuel_class
from core.data.terrain import get_elevation
from core.fire.fuel import base_ros
from core.geo import make_grid
from core.models import AOI, Layers, ProvenanceRecord

logger = logging.getLogger(__name__)


def build_layers(
    aoi: AOI, res_m: Optional[float] = None
) -> Tuple[Layers, List[ProvenanceRecord], List[str]]:
    """Assemble static terrain and fuel layers on a UTM Cartesian grid for an AOI.

    Execution sequence:
    1. Construct UTM GridSpec covering AOI (auto-coarsening res_m if cell count > MAX_GRID_CELLS).
    2. Ingest elevation raster from AWS Terrarium tiles via bilinear interpolation.
    3. Ingest land cover class raster from ESA WorldCover via windowed HTTP reads.
    4. Compute baseline rate-of-spread (base_ros) in metres/min.
    5. Track provenance records and surface warnings if fallbacks were engaged.

    Args:
        aoi: Area of Interest bounding box.
        res_m: Desired cell resolution in metres (defaults to Settings.GRID_RES_M).

    Returns:
        Tuple of:
        - Layers: Consolidated spatial data structure holding grid, elevation, fuel_class, base_ros.
        - List[ProvenanceRecord]: Data provenance audit records.
        - List[str]: Human-readable warnings emitted during assembly.
    """
    settings = get_settings()
    target_res = float(res_m) if res_m is not None else float(settings.GRID_RES_M)

    # 1. Generate Cartesian grid covering AOI in UTM
    grid = make_grid(aoi=aoi, res_m=target_res, max_cells=settings.MAX_GRID_CELLS)
    logger.info("Built grid for AOI: %dx%d cells at %.1fm resolution (EPSG:%d)", grid.nx, grid.ny, grid.res_m, grid.epsg)

    # 2. Ingest elevation
    elevation, prov_elev = get_elevation(grid)

    # 3. Ingest fuel class
    fuel_class, prov_fuel = get_fuel_class(grid)

    # 4. Compute base rate-of-spread (m/min)
    ros = base_ros(fuel_class)

    # 5. Check provenance and emit warnings
    warnings: List[str] = []
    provenance_list: List[ProvenanceRecord] = [prov_elev, prov_fuel]

    if prov_fuel.is_stale or "FUEL UNKNOWN" in prov_fuel.note:
        warn_msg = "WARNING: Land cover feed unavailable; using uniform grassland fallback (30)"
        warnings.append(warn_msg)
        logger.warning(warn_msg)

    if np.all(elevation == 0.0) or "FLAT" in prov_elev.note:
        warn_msg = "WARNING: Elevation data fallback to flat terrain"
        warnings.append(warn_msg)
        logger.warning(warn_msg)

    prov_dict = {
        "elevation": prov_elev.model_dump(),
        "fuel_class": prov_fuel.model_dump(),
    }

    layers = Layers(
        grid=grid,
        elevation=elevation,
        fuel_class=fuel_class,
        base_ros=ros,
        provenance=prov_dict,
    )

    return layers, provenance_list, warnings
