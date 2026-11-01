import type { AddLayerObject } from 'maplibre-gl';
import { LAYERS, SOURCES } from '../utils/layerConstants';

export function getTerrainLayers(): AddLayerObject[] {
  return [
    {
      id: LAYERS.TERRAIN_HILLSHADE,
      type: 'hillshade',
      source: SOURCES.TERRAIN_DEM,
      layout: {
        visibility: 'none', // Default to hidden so it never blacks out the basemap
      },
      paint: {
        'hillshade-exaggeration': 0.35,
        'hillshade-shadow-color': 'rgba(10, 10, 15, 0.5)',
        'hillshade-highlight-color': 'rgba(255, 255, 255, 0.2)',
        'hillshade-accent-color': 'rgba(30, 40, 50, 0.3)',
      },
    },
  ];
}

