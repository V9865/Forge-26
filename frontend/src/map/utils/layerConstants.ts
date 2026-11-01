/**
 * Layer and Source ID Constants for EmberRoute MapLibre GL JS implementation.
 */

export const SOURCES = {
  DETECTIONS: 'fire-detections',
  ARRIVAL_BANDS: 'arrival-bands',
  SETTLEMENTS: 'settlements',
  ROUTES: 'evacuation-routes',
  BASELINE_ROUTES: 'baseline-routes',
  SCENARIO_IGNITION: 'scenario-ignition',
  WIND: 'wind-indicators',
  TERRAIN_DEM: 'aws-terrarium-dem',
} as const;

export const LAYERS = {
  // Terrain Hillshade
  TERRAIN_HILLSHADE: 'terrain-hillshade',

  // Arrival Bands
  ARRIVAL_BANDS_FILL: 'arrival-bands-fill',
  ARRIVAL_BANDS_STROKE: 'arrival-bands-stroke',

  // Evacuation Routes
  BASELINE_ROUTES_CASING: 'baseline-routes-casing',
  BASELINE_ROUTES_LINE: 'baseline-routes-line',
  EVACUATION_ROUTES_CASING: 'evacuation-routes-casing',
  EVACUATION_ROUTES_GLOW: 'evacuation-routes-glow',
  EVACUATION_ROUTES_LINE: 'evacuation-routes-line',

  // Settlements
  SETTLEMENTS_HALO: 'settlements-halo',
  SETTLEMENTS_CIRCLE: 'settlements-circle',
  SETTLEMENTS_LABEL: 'settlements-label',

  // Fire Detections
  DETECTIONS_CLUSTERS: 'fire-detections-clusters',
  DETECTIONS_CLUSTER_COUNT: 'fire-detections-cluster-count',
  DETECTIONS_POINT_GLOW: 'fire-detections-point-glow',
  DETECTIONS_POINT: 'fire-detections-point',

  // Scenario Ignition Beacon
  SCENARIO_PULSE: 'scenario-ignition-pulse',
  SCENARIO_POINT: 'scenario-ignition-point',

  // Wind Indicators
  WIND_ARROW: 'wind-indicators-arrow',
  WIND_LABEL: 'wind-indicators-label',
} as const;

export const MAP_FONTS = ['Noto Sans Bold', 'Noto Sans Regular'];

export const DEFAULT_MAP_CENTER: [number, number] = [-4.0, 39.8];
export const DEFAULT_MAP_ZOOM = 5.5;

export const TERRAIN_TILES_URL =
  'https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png';
