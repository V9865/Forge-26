import type { Map, GeoJSONSource } from 'maplibre-gl';
import type { FeatureCollection } from 'geojson';
import { SOURCES } from '../utils/layerConstants';
import { emptyFeatureCollection } from '../utils/geoJsonValidation';

export function registerGeoJsonSources(map: Map): void {
  // 1. Fire Detections (Clustered)
  if (!map.getSource(SOURCES.DETECTIONS)) {
    map.addSource(SOURCES.DETECTIONS, {
      type: 'geojson',
      data: emptyFeatureCollection(),
      cluster: true,
      clusterMaxZoom: 14,
      clusterRadius: 40,
    });
  }

  // 2. Arrival Bands (Isochrones)
  if (!map.getSource(SOURCES.ARRIVAL_BANDS)) {
    map.addSource(SOURCES.ARRIVAL_BANDS, {
      type: 'geojson',
      data: emptyFeatureCollection(),
    });
  }

  // 3. Settlements
  if (!map.getSource(SOURCES.SETTLEMENTS)) {
    map.addSource(SOURCES.SETTLEMENTS, {
      type: 'geojson',
      data: emptyFeatureCollection(),
    });
  }

  // 4. Recommended Evacuation Routes
  if (!map.getSource(SOURCES.ROUTES)) {
    map.addSource(SOURCES.ROUTES, {
      type: 'geojson',
      data: emptyFeatureCollection(),
    });
  }

  // 5. Baseline Routes Cut by Fire
  if (!map.getSource(SOURCES.BASELINE_ROUTES)) {
    map.addSource(SOURCES.BASELINE_ROUTES, {
      type: 'geojson',
      data: emptyFeatureCollection(),
    });
  }

  // 6. Scenario Ignition Beacon
  if (!map.getSource(SOURCES.SCENARIO_IGNITION)) {
    map.addSource(SOURCES.SCENARIO_IGNITION, {
      type: 'geojson',
      data: emptyFeatureCollection(),
    });
  }

  // 7. Wind Indicators
  if (!map.getSource(SOURCES.WIND)) {
    map.addSource(SOURCES.WIND, {
      type: 'geojson',
      data: emptyFeatureCollection(),
    });
  }

  // 8. Overture Transportation Road Network
  if (!map.getSource(SOURCES.ROADS)) {
    map.addSource(SOURCES.ROADS, {
      type: 'geojson',
      data: emptyFeatureCollection(),
    });
  }
}

export function updateGeoJsonSource(
  map: Map,
  sourceId: string,
  data: FeatureCollection | null | undefined,
): void {
  const source = map.getSource(sourceId) as GeoJSONSource | undefined;
  if (!source) return;

  try {
    source.setData(data ?? emptyFeatureCollection());
  } catch (err) {
    console.warn(`[EmberRoute Map] Failed updating source ${sourceId}:`, err);
  }
}

