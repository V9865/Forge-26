/**
 * Coordinate and geographic utilities for EmberRoute MapLibre integration.
 * Strictly adheres to WGS84 [longitude, latitude] GeoJSON conventions.
 */

export function isValidLngLat(lng: number, lat: number): boolean {
  return (
    Number.isFinite(lng) &&
    Number.isFinite(lat) &&
    lng >= -180 &&
    lng <= 180 &&
    lat >= -90 &&
    lat <= 90
  );
}

export function isValidPointCoordinate(coord: unknown): coord is [number, number] {
  return (
    Array.isArray(coord) &&
    coord.length >= 2 &&
    typeof coord[0] === 'number' &&
    typeof coord[1] === 'number' &&
    isValidLngLat(coord[0], coord[1])
  );
}

export function cardinalFromDegrees(deg: number): string {
  const directions = [
    'N', 'NNE', 'NE', 'ENE',
    'E', 'ESE', 'SE', 'SSE',
    'S', 'SSW', 'SW', 'WSW',
    'W', 'WNW', 'NW', 'NNW',
  ];
  const normalized = ((deg % 360) + 360) % 360;
  const idx = Math.round(normalized / 22.5) % 16;
  return directions[idx];
}

/**
 * Returns spread direction from meteorological wind direction.
 * Open-Meteo wind is the direction wind comes FROM.
 * Spread direction is (dir + 180) % 360.
 */
export function spreadBearingFromWindDir(dirFromDeg: number): number {
  return ((dirFromDeg + 180) % 360 + 360) % 360;
}
