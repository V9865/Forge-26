import type { AddLayerObject } from 'maplibre-gl';
import { LAYERS, SOURCES } from '../utils/layerConstants';

export function getTerrainLayers(): AddLayerObject[] {
  return [
    {
      id: LAYERS.TERRAIN_HILLSHADE,
      type: 'hillshade',
      source: SOURCES.TERRAIN_DEM,
      layout: {
        visibility: 'visible',
      },
      paint: {
        'hillshade-exaggeration': 0.35,
        'hillshade-shadow-color': '#08080a',
        'hillshade-highlight-color': '#2a3540',
        'hillshade-accent-color': '#1a2028',
      },
    },
  ];
}
