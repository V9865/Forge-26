import type { StyleSpecification } from 'maplibre-gl';

/**
 * OpenFreeMap vector basemap style options.
 * Defaults to the rich Liberty style with clear topography, roads, and contrast.
 */
export const OPENFREEMAP_STYLES = {
  liberty: 'https://tiles.openfreemap.org/styles/liberty',
  dark: 'https://tiles.openfreemap.org/styles/dark',
  bright: 'https://tiles.openfreemap.org/styles/bright',
  positron: 'https://tiles.openfreemap.org/styles/positron',
} as const;

export type BasemapStyleKey = keyof typeof OPENFREEMAP_STYLES | 'osm';

export const DEFAULT_OPENFREEMAP_STYLE =
  (import.meta.env.VITE_MAP_STYLE_URL as string | undefined)?.trim() ||
  OPENFREEMAP_STYLES.liberty;

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

