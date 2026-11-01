import type { FeatureCollection, Geometry, GeoJsonProperties } from 'geojson';

export function emptyFeatureCollection<
  G extends Geometry = Geometry,
  P = GeoJsonProperties
>(): FeatureCollection<G, P> {
  return {
    type: 'FeatureCollection',
    features: [],
  };
}

export function sanitizeFeatureCollection<
  G extends Geometry = Geometry,
  P = GeoJsonProperties
>(fc: unknown): FeatureCollection<G, P> {
  if (
    !fc ||
    typeof fc !== 'object' ||
    (fc as any).type !== 'FeatureCollection' ||
    !Array.isArray((fc as any).features)
  ) {
    return emptyFeatureCollection<G, P>();
  }

  // Filter out features with null or unparseable geometry
  const validFeatures = (fc as any).features.filter((f: any) => {
    return (
      f &&
      typeof f === 'object' &&
      f.type === 'Feature' &&
      f.geometry &&
      typeof f.geometry === 'object' &&
      typeof f.geometry.type === 'string' &&
      Array.isArray(f.geometry.coordinates)
    );
  });

  return {
    type: 'FeatureCollection',
    features: validFeatures,
  };
}

