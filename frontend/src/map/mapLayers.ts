/**
 * EmberRoute — MapLibre Style Specification & Layer Registration
 *
 * Implements OpenFreeMap vector basemap integration with operational wildfire layers:
 * 1. Terrain Hillshade (AWS Terrarium DEM)
 * 2. Arrival Bands (Isochrones)
 * 3. Evacuation Routes (Safe fire-aware & cut baseline paths)
 * 4. Settlements & Shelters
 * 5. NASA FIRMS Fire Detections
 * 6. Scenario Ignition Beacon
 * 7. Meteorological Wind Indicators
 */

import type { Map } from 'maplibre-gl';
import { getTerrainLayers } from './layers/TerrainLayer';
import { getRoadLayers } from './layers/RoadLayer';
import { getFireSpreadLayers } from './layers/FireSpreadLayer';
import { getEvacuationRouteLayers } from './layers/EvacuationRouteLayer';
import { getSettlementLayers } from './layers/SettlementLayer';
import { getFireDetectionLayers } from './layers/FireDetectionLayer';
import { getWindLayers } from './layers/WindLayer';
import { registerGeoJsonSources } from './sources/geoJsonSources';
import { registerRasterSources } from './sources/rasterSources';

export {
  DEFAULT_OPENFREEMAP_STYLE,
  OPENFREEMAP_STYLES,
  type BasemapStyleKey,
  OPENFREEMAP_ATTRIBUTION,
  createFallbackRasterStyle,
} from './utils/mapStyle';
export { SOURCES, LAYERS, MAP_FONTS, DEFAULT_MAP_CENTER, DEFAULT_MAP_ZOOM } from './utils/layerConstants';

/**
 * Registers all sources and operational layers on a loaded MapLibre instance in strict z-order.
 */
export function setupOperationalLayers(map: Map): void {
  // 1. Register sources first
  registerRasterSources(map);
  registerGeoJsonSources(map);

  // 2. Add layers in bottom-to-top z-index order
  const layerGroups = [
    getTerrainLayers(),
    getRoadLayers(),
    getFireSpreadLayers(),
    getEvacuationRouteLayers(),
    getSettlementLayers(),
    getFireDetectionLayers(),
    getWindLayers(),
  ];

  for (const group of layerGroups) {
    for (const layer of group) {
      if (!map.getLayer(layer.id)) {
        try {
          map.addLayer(layer);
        } catch (err) {
          console.warn(`[EmberRoute Map] Layer registration deferred for ${layer.id}:`, err);
        }
      }
    }
  }
}
