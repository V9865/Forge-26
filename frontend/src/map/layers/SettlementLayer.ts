import type { AddLayerObject } from 'maplibre-gl';
import { LAYERS, SOURCES, MAP_FONTS } from '../utils/layerConstants';

export function getSettlementLayers(): AddLayerObject[] {
  return [
    {
      id: LAYERS.SETTLEMENTS_HALO,
      type: 'circle',
      source: SOURCES.SETTLEMENTS,
      layout: {
        visibility: 'visible',
      },
      paint: {
        'circle-radius': 9,
        'circle-color': '#0b0f14',
        'circle-opacity': 0.85,
      },
    },
    {
      id: LAYERS.SETTLEMENTS_CIRCLE,
      type: 'circle',
      source: SOURCES.SETTLEMENTS,
      layout: {
        visibility: 'visible',
      },
      paint: {
        'circle-radius': 6.5,
        'circle-color': [
          'match',
          ['get', 'status'],
          'EVACUATE',
          '#2ecc71',
          'TRAPPED',
          '#ff3b30',
          'ALREADY_BURNING',
          '#8b1a1a',
          /* default / NOT_THREATENED */
          '#657787',
        ],
        'circle-stroke-width': [
          'case',
          ['==', ['get', 'status'], 'ALREADY_BURNING'],
          2.5,
          ['==', ['get', 'isSelected'], true],
          3,
          1.5,
        ],
        'circle-stroke-color': [
          'case',
          ['==', ['get', 'status'], 'ALREADY_BURNING'],
          '#ffffff',
          ['==', ['get', 'isSelected'], true],
          '#ff6a2b',
          '#ffffff',
        ],
        'circle-stroke-opacity': [
          'case',
          ['==', ['get', 'status'], 'ALREADY_BURNING'],
          1.0,
          ['==', ['get', 'isSelected'], true],
          1.0,
          0.65,
        ],
      },
    },
    {
      id: LAYERS.SETTLEMENTS_LABEL,
      type: 'symbol',
      source: SOURCES.SETTLEMENTS,
      layout: {
        'text-field': ['get', 'name'],
        'text-font': MAP_FONTS,
        'text-size': 11,
        'text-offset': [0, 1.2],
        'text-anchor': 'top',
        'text-optional': true,
        visibility: 'visible',
      },
      paint: {
        'text-color': '#e6edf3',
        'text-halo-color': '#0b0f14',
        'text-halo-width': 1.8,
      },
    },
  ];
}
