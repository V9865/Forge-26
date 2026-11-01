import type { AddLayerObject } from 'maplibre-gl';
import { LAYERS, SOURCES, MAP_FONTS } from '../utils/layerConstants';

export function getFireDetectionLayers(): AddLayerObject[] {
  return [
    // 1. Clusters
    {
      id: LAYERS.DETECTIONS_CLUSTERS,
      type: 'circle',
      source: SOURCES.DETECTIONS,
      filter: ['has', 'point_count'],
      layout: {
        visibility: 'visible',
      },
      paint: {
        'circle-color': [
          'step',
          ['get', 'point_count'],
          '#ff6a2b',
          10,
          '#ff4500',
          50,
          '#d62828',
        ],
        'circle-radius': [
          'step',
          ['get', 'point_count'],
          14,
          10,
          18,
          50,
          24,
        ],
        'circle-opacity': 0.88,
        'circle-stroke-width': 2,
        'circle-stroke-color': '#ffffff',
        'circle-stroke-opacity': 0.6,
      },
    },
    {
      id: LAYERS.DETECTIONS_CLUSTER_COUNT,
      type: 'symbol',
      source: SOURCES.DETECTIONS,
      filter: ['has', 'point_count'],
      layout: {
        'text-field': '{point_count_abbreviated}',
        'text-size': 11,
        'text-font': MAP_FONTS,
        visibility: 'visible',
      },
      paint: {
        'text-color': '#ffffff',
      },
    },

    // 2. Individual Hotspots
    {
      id: LAYERS.DETECTIONS_POINT_GLOW,
      type: 'circle',
      source: SOURCES.DETECTIONS,
      filter: ['!', ['has', 'point_count']],
      layout: {
        visibility: 'visible',
      },
      paint: {
        'circle-color': '#ff6a2b',
        'circle-radius': 9,
        'circle-opacity': 0.45,
        'circle-blur': 0.5,
      },
    },
    {
      id: LAYERS.DETECTIONS_POINT,
      type: 'circle',
      source: SOURCES.DETECTIONS,
      filter: ['!', ['has', 'point_count']],
      layout: {
        visibility: 'visible',
      },
      paint: {
        'circle-color': '#ff6a2b',
        'circle-radius': 4.5,
        'circle-stroke-width': 1.5,
        'circle-stroke-color': '#ffc080',
        'circle-opacity': 0.95,
      },
    },

    // 3. Scenario Ignition Beacon
    {
      id: LAYERS.SCENARIO_PULSE,
      type: 'circle',
      source: SOURCES.SCENARIO_IGNITION,
      layout: {
        visibility: 'visible',
      },
      paint: {
        'circle-radius': 18,
        'circle-color': '#f5a524',
        'circle-opacity': 0.35,
        'circle-blur': 0.6,
      },
    },
    {
      id: LAYERS.SCENARIO_POINT,
      type: 'circle',
      source: SOURCES.SCENARIO_IGNITION,
      layout: {
        visibility: 'visible',
      },
      paint: {
        'circle-radius': 7.5,
        'circle-color': '#f5a524',
        'circle-stroke-width': 2.5,
        'circle-stroke-color': '#ffffff',
        'circle-opacity': 1.0,
      },
    },
  ];
}
