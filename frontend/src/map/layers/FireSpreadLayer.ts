import type { AddLayerObject } from 'maplibre-gl';
import { LAYERS, SOURCES } from '../utils/layerConstants';

export function getFireSpreadLayers(): AddLayerObject[] {
  return [
    {
      id: LAYERS.ARRIVAL_BANDS_FILL,
      type: 'fill',
      source: SOURCES.ARRIVAL_BANDS,
      layout: {
        visibility: 'visible',
      },
      paint: {
        'fill-color': [
          'interpolate',
          ['linear'],
          ['get', 't_min'],
          120,
          '#ff3b30',
          240,
          '#ff8a00',
          480,
          '#ffc400',
          720,
          '#ffe58a',
        ],
        'fill-opacity': [
          'interpolate',
          ['linear'],
          ['get', 't_min'],
          120,
          0.6,
          240,
          0.5,
          480,
          0.45,
          720,
          0.4,
        ],
      },
    },
    {
      id: LAYERS.ARRIVAL_BANDS_STROKE,
      type: 'line',
      source: SOURCES.ARRIVAL_BANDS,
      layout: {
        visibility: 'visible',
      },
      paint: {
        'line-color': [
          'interpolate',
          ['linear'],
          ['get', 't_min'],
          120,
          '#ff3b30',
          240,
          '#ff8a00',
          480,
          '#ffc400',
          720,
          '#ffe58a',
        ],
        'line-width': 1.5,
        'line-opacity': 0.85,
      },
    },
  ];
}
