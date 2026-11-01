import type { AddLayerObject } from 'maplibre-gl';
import { LAYERS, SOURCES } from '../utils/layerConstants';

/**
 * Road network styling for Overture Transportation segments.
 * Placed beneath evacuation routes and settlements for clear visual hierarchy.
 */
export function getRoadLayers(): AddLayerObject[] {
  return [
    {
      id: LAYERS.ROADS_CASING,
      type: 'line',
      source: SOURCES.ROADS,
      layout: {
        'line-cap': 'round',
        'line-join': 'round',
        visibility: 'visible',
      },
      paint: {
        'line-color': '#080c10',
        'line-width': [
          'interpolate',
          ['linear'],
          ['zoom'],
          8, 1.5,
          12, 3.5,
          16, 7.0,
        ],
        'line-opacity': 0.75,
      },
    },
    {
      id: LAYERS.ROADS_LINE,
      type: 'line',
      source: SOURCES.ROADS,
      layout: {
        'line-cap': 'round',
        'line-join': 'round',
        visibility: 'visible',
      },
      paint: {
        'line-color': [
          'match',
          ['get', 'class'],
          'motorway', '#4fc3f7',
          'primary', '#38bdf8',
          'secondary', '#818cf8',
          'tertiary', '#94a3b8',
          'residential', '#64748b',
          'living_street', '#475569',
          'service', '#334155',
          'track', '#475569',
          /* default / unclassified */ '#64748b',
        ],
        'line-width': [
          'interpolate',
          ['linear'],
          ['zoom'],
          8, 0.8,
          12, 2.0,
          16, 4.5,
        ],
        'line-opacity': 0.85,
      },
    },
  ];
}

