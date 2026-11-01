import type { StyleSpecification } from 'maplibre-gl';

/**
 * OpenFreeMap vector basemap style URL.
 * Defaults to the official OpenFreeMap dark style: https://tiles.openfreemap.org/styles/dark
 * Configurable via VITE_MAP_STYLE_URL in environment.
 */
export const DEFAULT_OPENFREEMAP_STYLE =
  (import.meta.env.VITE_MAP_STYLE_URL as string | undefined)?.trim() ||
  'https://tiles.openfreemap.org/styles/dark';

export const OPENFREEMAP_ATTRIBUTION =
  '<a href="https://openfreemap.org" target="_blank" rel="noreferrer">OpenFreeMap</a> &copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer">OpenStreetMap</a> contributors';

export const OSM_RASTER_TILES = [
  'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
];

/**
 * Resilient fallback style spec if the primary OpenFreeMap vector style fails to load.
 */
export function createFallbackRasterStyle(): StyleSpecification {
  return {
    version: 8,
    glyphs: 'https://demotiles.maplibre.org/font/{fontstack}/{range}.pbf',
    sources: {
      'osm-fallback': {
        type: 'raster',
        tiles: OSM_RASTER_TILES,
        tileSize: 256,
        attribution: OPENFREEMAP_ATTRIBUTION,
        maxzoom: 19,
      },
    },
    layers: [
      {
        id: 'osm-fallback-tiles',
        type: 'raster',
        source: 'osm-fallback',
        minzoom: 0,
        maxzoom: 22,
      },
    ],
  };
}
