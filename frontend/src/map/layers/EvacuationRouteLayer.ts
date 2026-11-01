import type { AddLayerObject } from 'maplibre-gl';
import { LAYERS, SOURCES } from '../utils/layerConstants';

export function getEvacuationRouteLayers(): AddLayerObject[] {
  return [
    // 1. Naive Baseline Routes (Cut by fire - dashed warning style)
    {
      id: LAYERS.BASELINE_ROUTES_CASING,
      type: 'line',
      source: SOURCES.BASELINE_ROUTES,
      layout: {
        'line-cap': 'round',
        'line-join': 'round',
        visibility: 'visible',
      },
      paint: {
        'line-color': '#0b0f14',
        'line-width': 5.5,
        'line-opacity': 0.9,
      },
    },
    {
      id: LAYERS.BASELINE_ROUTES_LINE,
      type: 'line',
      source: SOURCES.BASELINE_ROUTES,
      layout: {
        'line-cap': 'round',
        'line-join': 'round',
        visibility: 'visible',
      },
      paint: {
        'line-color': '#ff1744',
        'line-width': 3.5,
        'line-dasharray': [2, 2],
        'line-opacity': 1.0,
      },
    },

    // 2. Fire-Aware Recommended Evacuation Routes (Safe path)
    {
      id: LAYERS.EVACUATION_ROUTES_CASING,
      type: 'line',
      source: SOURCES.ROUTES,
      layout: {
        'line-cap': 'round',
        'line-join': 'round',
        visibility: 'visible',
      },
      paint: {
        'line-color': '#0b0f14',
        'line-width': 7,
        'line-opacity': 0.95,
      },
    },
    {
      id: LAYERS.EVACUATION_ROUTES_GLOW,
      type: 'line',
      source: SOURCES.ROUTES,
      layout: {
        'line-cap': 'round',
        'line-join': 'round',
        visibility: 'visible',
      },
      paint: {
        'line-color': '#00ff88',
        'line-width': 10,
        'line-opacity': 0.45,
        'line-blur': 2.5,
      },
    },
    {
      id: LAYERS.EVACUATION_ROUTES_LINE,
      type: 'line',
      source: SOURCES.ROUTES,
      layout: {
        'line-cap': 'round',
        'line-join': 'round',
        visibility: 'visible',
      },
      paint: {
        'line-color': '#00e676',
        'line-width': 4.5,
        'line-opacity': 1.0,
      },
    },
  ];
}
