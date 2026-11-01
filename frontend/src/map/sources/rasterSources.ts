import type { Map } from 'maplibre-gl';
import { SOURCES, TERRAIN_TILES_URL } from '../utils/layerConstants';

export function registerRasterSources(map: Map): void {
  // AWS Terrarium DEM raster source for hillshade
  if (!map.getSource(SOURCES.TERRAIN_DEM)) {
    try {
      map.addSource(SOURCES.TERRAIN_DEM, {
        type: 'raster-dem',
        tiles: [TERRAIN_TILES_URL],
        encoding: 'terrarium',
        tileSize: 256,
        maxzoom: 15,
      });
    } catch (err) {
      console.warn('[EmberRoute Map] Optional AWS Terrarium raster-dem source registration deferred:', err);
    }
  }
}

