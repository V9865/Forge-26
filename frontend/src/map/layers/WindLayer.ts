import type { AddLayerObject } from 'maplibre-gl';
import { LAYERS, SOURCES, MAP_FONTS } from '../utils/layerConstants';

export function getWindLayers(): AddLayerObject[] {
  return [
    {
      id: LAYERS.WIND_ARROW,
      type: 'symbol',
      source: SOURCES.WIND,
      layout: {
        'text-field': '➤',
        'text-size': 22,
        'text-rotate': ['get', 'bearing'],
        'text-rotation-alignment': 'map',
        'text-allow-overlap': true,
        'text-ignore-placement': true,
        visibility: 'visible',
      },
      paint: {
        'text-color': '#00d2ff',
        'text-halo-color': '#0b0f14',
        'text-halo-width': 2,
      },
    },
    {
      id: LAYERS.WIND_LABEL,
      type: 'symbol',
      source: SOURCES.WIND,
      layout: {
        'text-field': ['get', 'label'],
        'text-font': MAP_FONTS,
        'text-size': 11,
        'text-offset': [0, 1.4],
        'text-anchor': 'top',
        'text-allow-overlap': true,
        'text-ignore-placement': true,
        visibility: 'visible',
      },
      paint: {
        'text-color': '#00d2ff',
        'text-halo-color': '#0b0f14',
        'text-halo-width': 2,
      },
    },
  ];
}

