/**
 * EmberRoute — MapLibre Style Specification & Layer Configurations
 *
 * Implements the dark basemap (Carto Dark) with OSM fallback,
 * arrival-time band polygon styling (t_min in minutes), settlement markers with white rings,
 * fire detection clustering, and dual route styling.
 */

import type { StyleSpecification } from 'maplibre-gl';

// ── Basemap tile endpoints ───────────────────────────────────────────────────

const cartoKey = (import.meta.env.VITE_CARTO_API_KEY as string | undefined)?.trim() || '';

export const CARTO_DARK_TILES = cartoKey
  ? [
      `https://a.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png?key=${cartoKey}`,
      `https://b.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png?key=${cartoKey}`,
      `https://c.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png?key=${cartoKey}`,
      `https://d.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png?key=${cartoKey}`,
    ]
  : [
      'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
    ];

export const OSM_FALLBACK_TILES = [
  'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
];

export const CARTO_ATTRIBUTION =
  '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions" target="_blank" rel="noreferrer">CARTO</a>';

export const OSM_ATTRIBUTION =
  '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer">OpenStreetMap</a> contributors';

// ── Initial MapLibre Style Spec ──────────────────────────────────────────────

export function createBaseMapStyle(useFallback = false): StyleSpecification {
  return {
    version: 8,
    sources: {
      basemap: {
        type: 'raster',
        tiles: useFallback ? OSM_FALLBACK_TILES : CARTO_DARK_TILES,
        tileSize: 256,
        attribution: useFallback ? OSM_ATTRIBUTION : CARTO_ATTRIBUTION,
        maxzoom: 19,
      },
      'fire-detections': {
        type: 'geojson',
        data: { type: 'FeatureCollection', features: [] },
        cluster: true,
        clusterMaxZoom: 14,
        clusterRadius: 40,
      },
      'arrival-bands': {
        type: 'geojson',
        data: { type: 'FeatureCollection', features: [] },
      },
      'evacuation-routes': {
        type: 'geojson',
        data: { type: 'FeatureCollection', features: [] },
      },
      'baseline-routes': {
        type: 'geojson',
        data: { type: 'FeatureCollection', features: [] },
      },
      settlements: {
        type: 'geojson',
        data: { type: 'FeatureCollection', features: [] },
      },
      'scenario-ignition': {
        type: 'geojson',
        data: { type: 'FeatureCollection', features: [] },
      },
    },
    layers: [
      // 1. Basemap raster layer
      {
        id: 'basemap-tiles',
        type: 'raster',
        source: 'basemap',
        minzoom: 0,
        maxzoom: 22,
      },

      // 2. Arrival Bands Fill (Layered below roads & settlements, keyed on t_min minutes)
      {
        id: 'arrival-bands-fill',
        type: 'fill',
        source: 'arrival-bands',
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
            0.55,
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
        id: 'arrival-bands-stroke',
        type: 'line',
        source: 'arrival-bands',
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
          'line-opacity': 0.8,
        },
      },

      // 3. Naive Baseline Routes (Cut by fire - dashed warning style)
      {
        id: 'baseline-routes-line',
        type: 'line',
        source: 'baseline-routes',
        paint: {
          'line-color': '#ff3b30',
          'line-width': 2.5,
          'line-dasharray': [2, 2],
          'line-opacity': 0.75,
        },
      },

      // 4. Fire-Aware Recommended Evacuation Routes (Safe path)
      {
        id: 'evacuation-routes-glow',
        type: 'line',
        source: 'evacuation-routes',
        paint: {
          'line-color': '#2ecc71',
          'line-width': 7,
          'line-opacity': 0.25,
          'line-blur': 2,
        },
      },
      {
        id: 'evacuation-routes-line',
        type: 'line',
        source: 'evacuation-routes',
        paint: {
          'line-color': '#2ecc71',
          'line-width': 3.5,
          'line-opacity': 0.95,
        },
      },

      // 5. Fire Detection Clusters
      {
        id: 'fire-detections-clusters',
        type: 'circle',
        source: 'fire-detections',
        filter: ['has', 'point_count'],
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
          'circle-opacity': 0.85,
          'circle-stroke-width': 2,
          'circle-stroke-color': '#ffffff',
          'circle-stroke-opacity': 0.5,
        },
      },
      {
        id: 'fire-detections-cluster-count',
        type: 'symbol',
        source: 'fire-detections',
        filter: ['has', 'point_count'],
        layout: {
          'text-field': '{point_count_abbreviated}',
          'text-size': 11,
          'text-font': ['Open Sans Semibold', 'Arial Unicode MS Bold'],
        },
        paint: {
          'text-color': '#ffffff',
        },
      },

      // 6. Individual Fire Detections
      {
        id: 'fire-detections-point-glow',
        type: 'circle',
        source: 'fire-detections',
        filter: ['!', ['has', 'point_count']],
        paint: {
          'circle-color': '#ff6a2b',
          'circle-radius': 8,
          'circle-opacity': 0.4,
          'circle-blur': 0.5,
        },
      },
      {
        id: 'fire-detections-point',
        type: 'circle',
        source: 'fire-detections',
        filter: ['!', ['has', 'point_count']],
        paint: {
          'circle-color': '#ff6a2b',
          'circle-radius': 4.5,
          'circle-stroke-width': 1.5,
          'circle-stroke-color': '#ffc080',
          'circle-opacity': 0.95,
        },
      },

      // 7. Settlement Markers
      {
        id: 'settlements-halo',
        type: 'circle',
        source: 'settlements',
        paint: {
          'circle-radius': 9,
          'circle-color': '#0b0f14',
          'circle-opacity': 0.8,
        },
      },
      {
        id: 'settlements-circle',
        type: 'circle',
        source: 'settlements',
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
            // ALREADY_BURNING has prominent white ring
            ['==', ['get', 'status'], 'ALREADY_BURNING'],
            2.5,
            // Selected settlement highlighted with bold border
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
            0.6,
          ],
        },
      },

      // 8. Settlement Labels
      {
        id: 'settlements-label',
        type: 'symbol',
        source: 'settlements',
        layout: {
          'text-field': ['get', 'name'],
          'text-font': ['Open Sans Semibold', 'Arial Unicode MS Bold'],
          'text-size': 11,
          'text-offset': [0, 1.2],
          'text-anchor': 'top',
          'text-optional': true,
        },
        paint: {
          'text-color': '#e6edf3',
          'text-halo-color': '#0b0f14',
          'text-halo-width': 1.5,
        },
      },

      // 9. Scenario Ignition Point (Distinctive beacon in SCENARIO mode)
      {
        id: 'scenario-ignition-pulse',
        type: 'circle',
        source: 'scenario-ignition',
        paint: {
          'circle-radius': 16,
          'circle-color': '#f5a524',
          'circle-opacity': 0.35,
          'circle-blur': 0.5,
        },
      },
      {
        id: 'scenario-ignition-point',
        type: 'circle',
        source: 'scenario-ignition',
        paint: {
          'circle-radius': 7,
          'circle-color': '#f5a524',
          'circle-stroke-width': 2.5,
          'circle-stroke-color': '#ffffff',
          'circle-opacity': 1.0,
        },
      },
    ],
  };
}

