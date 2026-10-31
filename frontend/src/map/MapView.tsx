/**
 * MapView — MapLibre GL JS lifecycle and layer management component.
 */

import { useEffect, useRef, useState } from 'react';
import {
  Map,
  NavigationControl,
  Popup,
  LngLatBounds,
  type MapMouseEvent,
  type GeoJSONSource,
  type ErrorEvent,
} from 'maplibre-gl';
import { createBaseMapStyle, OSM_FALLBACK_TILES, OSM_ATTRIBUTION } from './mapLayers';
import type { MapDataProps, MapLayerVisibility } from './mapTypes';
import { formatArrivalHours } from '@/utils/format';

interface MapViewProps extends MapDataProps {
  visibility: MapLayerVisibility;
  timeFilterHours: number;
  onBoundsChange?: (bounds: [number, number, number, number]) => void;
}

export function MapView({
  detections = [],
  arrivalBands = [],
  settlements = [],
  routes = [],
  selectedSettlementId,
  onSelectSettlement,
  scenarioIgnition,
  onSelectIgnition,
  isScenarioMode = false,
  visibility,
  timeFilterHours,
}: MapViewProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<Map | null>(null);
  const popupRef = useRef<Popup | null>(null);
  const hasSwitchedToFallbackRef = useRef(false);
  const [mapLoaded, setMapLoaded] = useState(false);
  const [isUsingFallback, setIsUsingFallback] = useState(false);

  // ── 1. Map Initialization & ResizeObserver ──────────────────────────────────
  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;

    // Initialize map with default center (global view or Mediterranean wildfire risk area)
    const map = new Map({
      container: containerRef.current,
      style: createBaseMapStyle(false),
      center: [-4.0, 39.8],
      zoom: 5.5,
      pitch: 0,
      bearing: 0,
      attributionControl: { compact: true },
    });

    // Add navigation controls (zoom, compass, pitch reset)
    map.addControl(new NavigationControl({ showCompass: true }), 'top-right');

    map.on('load', () => {
      setMapLoaded(true);
    });

    // Robust Fallback Detection:
    // If Carto dark tiles fail to load, cleanly hot-swap the raster source to OSM Standard
    // without destroying the map instance or triggering an unmount/remount loop.
    map.on('error', (e: ErrorEvent) => {
      const isCartoError =
        e.error &&
        (e.error.message.includes('basemaps.cartocdn.com') ||
          e.error.message.includes('carto') ||
          e.error.message.includes('basemap'));

      if (isCartoError && !hasSwitchedToFallbackRef.current) {
        hasSwitchedToFallbackRef.current = true;

        try {
          if (map.getLayer('basemap-tiles')) {
            map.removeLayer('basemap-tiles');
          }
          if (map.getSource('basemap')) {
            map.removeSource('basemap');
          }

          map.addSource('basemap', {
            type: 'raster',
            tiles: OSM_FALLBACK_TILES,
            tileSize: 256,
            attribution: OSM_ATTRIBUTION,
            maxzoom: 19,
          });

          // Insert back underneath all vector data layers
          const beforeLayerId = map.getLayer('arrival-bands-fill') ? 'arrival-bands-fill' : undefined;
          map.addLayer(
            {
              id: 'basemap-tiles',
              type: 'raster',
              source: 'basemap',
              minzoom: 0,
              maxzoom: 22,
            },
            beforeLayerId,
          );

          setIsUsingFallback(true);
        } catch {
          // Fallback swap completed or style transition in flight
        }
      }
    });

    // ResizeObserver: auto-call map.resize() on sidebar/drawer toggles and container changes
    const resizeObserver = new ResizeObserver(() => {
      if (mapRef.current) {
        mapRef.current.resize();
      }
    });

    if (containerRef.current) {
      resizeObserver.observe(containerRef.current);
    }

    mapRef.current = map;

    return () => {
      resizeObserver.disconnect();
      popupRef.current?.remove();
      map.remove();
      mapRef.current = null;
      setMapLoaded(false);
    };
  }, []); // Run ONCE on mount — never remount on fallback state changes

  // ── 2. Click Handling (Settlements, Clusters, Scenario Ignition) ────────────
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapLoaded) return;

    // Click on settlements
    const handleSettlementClick = (e: MapMouseEvent) => {
      const features = map.queryRenderedFeatures(e.point, { layers: ['settlements-circle'] });
      if (!features.length) return;

      const f = features[0];
      const props = f.properties;
      const coords = (f.geometry as GeoJSON.Point).coordinates as [number, number];
      const settlementId = props?.id as string | undefined;

      if (settlementId && onSelectSettlement) {
        onSelectSettlement(settlementId);
      }

      popupRef.current?.remove();
      const popup = new Popup({ offset: 12, className: 'ember-map-popup' })
        .setLngLat(coords)
        .setHTML(`
          <div style="font-family: inherit; font-size: 12px; color: #e6edf3; background: #121821; padding: 6px 8px; border-radius: 4px; border: 1px solid #162733;">
            <div style="font-weight: 700; margin-bottom: 2px;">${props?.name || 'Settlement'}</div>
            <div style="color: #8b98a9; font-size: 11px;">Status: <span style="font-weight: 600; color: #ff6a2b;">${props?.status || 'UNKNOWN'}</span></div>
            ${props?.fire_arrival_h !== undefined ? `<div style="color: #8b98a9; font-size: 11px;">Fire arrival: <span style="font-family: monospace;">+${props.fire_arrival_h}h</span></div>` : ''}
            ${props?.depart_by ? `<div style="color: #8b98a9; font-size: 11px;">Depart by: <span style="font-family: monospace;">${props.depart_by}</span></div>` : ''}
          </div>
        `)
        .addTo(map);

      popupRef.current = popup;
    };

    // Click on fire detections
    const handleDetectionClick = (e: MapMouseEvent) => {
      const features = map.queryRenderedFeatures(e.point, { layers: ['fire-detections-point'] });
      if (!features.length) return;

      const f = features[0];
      const props = f.properties;
      const coords = (f.geometry as GeoJSON.Point).coordinates as [number, number];

      popupRef.current?.remove();
      const popup = new Popup({ offset: 10, className: 'ember-map-popup' })
        .setLngLat(coords)
        .setHTML(`
          <div style="font-family: inherit; font-size: 11px; color: #e6edf3; background: #121821; padding: 6px 8px; border-radius: 4px; border: 1px solid #162733;">
            <div style="font-weight: 700; color: #ff6a2b; margin-bottom: 2px;">NASA FIRMS Detection</div>
            <div style="color: #8b98a9;">Coords: <span style="font-family: monospace;">${coords[1].toFixed(4)}°N, ${coords[0].toFixed(4)}°E</span></div>
            ${props?.confidence ? `<div style="color: #8b98a9;">Confidence: <span>${props.confidence}</span></div>` : ''}
            ${props?.brightness ? `<div style="color: #8b98a9;">Brightness: <span>${props.brightness} K</span></div>` : ''}
            ${props?.timestamp ? `<div style="color: #8b98a9;">Detected: <span style="font-family: monospace;">${props.timestamp}</span></div>` : ''}
          </div>
        `)
        .addTo(map);

      popupRef.current = popup;
    };

    // Click on clusters to zoom in
    const handleClusterClick = (e: MapMouseEvent) => {
      const features = map.queryRenderedFeatures(e.point, { layers: ['fire-detections-clusters'] });
      if (!features.length) return;

      const clusterId = features[0].properties?.cluster_id;
      const source = map.getSource('fire-detections') as GeoJSONSource | undefined;
      if (source && clusterId !== undefined) {
        source.getClusterExpansionZoom(clusterId).then((zoom: number) => {
          const coords = (features[0].geometry as GeoJSON.Point).coordinates as [number, number];
          map.easeTo({ center: coords, zoom: zoom ?? map.getZoom() + 2 });
        });
      }
    };

    // Click on map to place Scenario Ignition Point
    const handleMapClick = (e: MapMouseEvent) => {
      if (!isScenarioMode || !onSelectIgnition) return;

      // Ensure click was not on a settlement or interactive feature
      const interactiveFeatures = map.queryRenderedFeatures(e.point, {
        layers: ['settlements-circle', 'fire-detections-clusters', 'fire-detections-point'],
      });
      if (interactiveFeatures.length > 0) return;

      onSelectIgnition({
        lat: e.lngLat.lat,
        lng: e.lngLat.lng,
      });
    };

    // Cursor styling
    const setPointer = () => {
      map.getCanvas().style.cursor = 'pointer';
    };
    const resetPointer = () => {
      map.getCanvas().style.cursor = isScenarioMode ? 'crosshair' : '';
    };

    map.on('click', 'settlements-circle', handleSettlementClick);
    map.on('click', 'fire-detections-point', handleDetectionClick);
    map.on('click', 'fire-detections-clusters', handleClusterClick);
    map.on('click', handleMapClick);

    map.on('mouseenter', 'settlements-circle', setPointer);
    map.on('mouseleave', 'settlements-circle', resetPointer);
    map.on('mouseenter', 'fire-detections-point', setPointer);
    map.on('mouseleave', 'fire-detections-point', resetPointer);
    map.on('mouseenter', 'fire-detections-clusters', setPointer);
    map.on('mouseleave', 'fire-detections-clusters', resetPointer);

    return () => {
      map.off('click', 'settlements-circle', handleSettlementClick);
      map.off('click', 'fire-detections-point', handleDetectionClick);
      map.off('click', 'fire-detections-clusters', handleClusterClick);
      map.off('click', handleMapClick);

      map.off('mouseenter', 'settlements-circle', setPointer);
      map.off('mouseleave', 'settlements-circle', resetPointer);
      map.off('mouseenter', 'fire-detections-point', setPointer);
      map.off('mouseleave', 'fire-detections-point', resetPointer);
      map.off('mouseenter', 'fire-detections-clusters', setPointer);
      map.off('mouseleave', 'fire-detections-clusters', resetPointer);
    };
  }, [mapLoaded, onSelectSettlement, onSelectIgnition, isScenarioMode]);

  // ── 3. Update GeoJSON Sources ──────────────────────────────────────────────
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapLoaded) return;

    // A. Fire detections source
    const detectionsSource = map.getSource('fire-detections') as GeoJSONSource | undefined;
    if (detectionsSource) {
      const geojson: GeoJSON.FeatureCollection<GeoJSON.Point> = {
        type: 'FeatureCollection',
        features: detections.map((d, index) => ({
          type: 'Feature',
          id: index,
          properties: {
            confidence: d.confidence,
            brightness: d.brightness,
            timestamp: d.timestamp,
            satellite: d.satellite,
          },
          geometry: {
            type: 'Point',
            coordinates: [d.longitude, d.latitude],
          },
        })),
      };
      detectionsSource.setData(geojson);
    }

    // B. Arrival bands source — Wavefront progressive revelation (0 to 12 hours)
    // Boundary behavior:
    // - At 0h: 0 bands appear (future bands never appear prematurely)
    // - At 2h: 0–2h band appears (1 band)
    // - At 4h: 0–2h and 2–4h bands appear (2 bands)
    // - At 8h: 0–2h, 2–4h, 4–8h bands appear (3 bands; 8–12h does not appear prematurely)
    // - At 12h: all 4 bands appear (4 bands)
    const arrivalSource = map.getSource('arrival-bands') as GeoJSONSource | undefined;
    if (arrivalSource) {
      const filteredBands = arrivalBands.filter(
        (b) => timeFilterHours > 0 && b.hours_min < timeFilterHours,
      );
      const geojson: GeoJSON.FeatureCollection = {
        type: 'FeatureCollection',
        features: filteredBands.map((band, idx) => ({
          type: 'Feature',
          id: idx,
          properties: {
            hours_min: band.hours_min,
            hours_max: band.hours_max,
          },
          geometry: band.geometry,
        })),
      };
      arrivalSource.setData(geojson);
    }

    // C. Settlements source
    const settlementsSource = map.getSource('settlements') as GeoJSONSource | undefined;
    if (settlementsSource) {
      const geojson: GeoJSON.FeatureCollection<GeoJSON.Point> = {
        type: 'FeatureCollection',
        features: settlements.map((s) => ({
          type: 'Feature',
          id: s.id,
          properties: {
            id: s.id,
            name: s.name,
            status: s.status,
            fire_arrival_h: s.fire_arrival_h,
            depart_by: s.depart_by,
            isSelected: s.id === selectedSettlementId,
          },
          geometry: {
            type: 'Point',
            coordinates: s.coordinates,
          },
        })),
      };
      settlementsSource.setData(geojson);
    }

    // D. Safe fire-aware evacuation routes
    const routesSource = map.getSource('evacuation-routes') as GeoJSONSource | undefined;
    if (routesSource) {
      const safeRoutes = routes.filter((r) => r.is_fire_aware && !r.is_baseline);
      const geojson: GeoJSON.FeatureCollection = {
        type: 'FeatureCollection',
        features: safeRoutes.map((r) => ({
          type: 'Feature',
          id: r.id,
          properties: {
            id: r.id,
            settlement_id: r.settlement_id,
            distance_km: r.distance_km,
            duration_min: r.duration_min,
          },
          geometry: r.geometry,
        })),
      };
      routesSource.setData(geojson);
    }

    // E. Naive baseline routes (cut segments)
    const baselineSource = map.getSource('baseline-routes') as GeoJSONSource | undefined;
    if (baselineSource) {
      const baseRoutes = routes.filter((r) => r.is_baseline);
      const geojson: GeoJSON.FeatureCollection = {
        type: 'FeatureCollection',
        features: baseRoutes.map((r) => ({
          type: 'Feature',
          id: r.id,
          properties: {
            id: r.id,
            settlement_id: r.settlement_id,
            cut_segments: r.cut_segments,
            cut_reason: r.cut_reason,
          },
          geometry: r.geometry,
        })),
      };
      baselineSource.setData(geojson);
    }

    // F. Scenario ignition point — strictly isolated:
    // Only rendered when BOTH isScenarioMode AND scenarioIgnition are present.
    // Switching to LIVE mode immediately clears the feature collection.
    const ignitionSource = map.getSource('scenario-ignition') as GeoJSONSource | undefined;
    if (ignitionSource) {
      const features: GeoJSON.Feature<GeoJSON.Point>[] =
        isScenarioMode && scenarioIgnition
          ? [
              {
                type: 'Feature',
                properties: { type: 'scenario-ignition' },
                geometry: {
                  type: 'Point',
                  coordinates: [scenarioIgnition.lng, scenarioIgnition.lat],
                },
              },
            ]
          : [];
      ignitionSource.setData({ type: 'FeatureCollection', features });
    }
  }, [
    mapLoaded,
    detections,
    arrivalBands,
    settlements,
    routes,
    selectedSettlementId,
    scenarioIgnition,
    isScenarioMode,
    timeFilterHours,
  ]);

  // ── 4. Update Layer Visibilities ───────────────────────────────────────────
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapLoaded) return;

    const setVisibility = (layerIds: string[], visible: boolean) => {
      const val = visible ? 'visible' : 'none';
      for (const id of layerIds) {
        if (map.getLayer(id)) {
          map.setLayoutProperty(id, 'visibility', val);
        }
      }
    };

    setVisibility(
      ['fire-detections-clusters', 'fire-detections-cluster-count', 'fire-detections-point', 'fire-detections-point-glow'],
      visibility.detections,
    );
    setVisibility(['arrival-bands-fill', 'arrival-bands-stroke'], visibility.arrivalBands);
    setVisibility(['settlements-circle', 'settlements-halo', 'settlements-label'], visibility.settlements);
    setVisibility(['evacuation-routes-line', 'evacuation-routes-glow'], visibility.routes);
    setVisibility(['baseline-routes-line'], visibility.baselineRoutes);

    // Scenario beacon layer visibility strictly synchronized with mode and state
    setVisibility(
      ['scenario-ignition-point', 'scenario-ignition-pulse'],
      isScenarioMode && Boolean(scenarioIgnition),
    );
  }, [mapLoaded, visibility, isScenarioMode, scenarioIgnition]);

  // ── 5. Auto Fit-to-Bounds helper ───────────────────────────────────────────
  const fitToFeatures = () => {
    const map = mapRef.current;
    if (!map) return;

    const coords: [number, number][] = [];
    detections.forEach((d) => coords.push([d.longitude, d.latitude]));
    settlements.forEach((s) => coords.push(s.coordinates));
    if (isScenarioMode && scenarioIgnition) {
      coords.push([scenarioIgnition.lng, scenarioIgnition.lat]);
    }

    if (coords.length === 0) {
      map.easeTo({ center: [-4.0, 39.8], zoom: 5.5 });
      return;
    }

    const bounds = new LngLatBounds(coords[0], coords[0]);
    for (const c of coords) {
      bounds.extend(c);
    }
    map.fitBounds(bounds, { padding: 48, maxZoom: 13, duration: 800 });
  };

  return (
    <div className="relative w-full h-full min-h-0 min-w-0">
      <div ref={containerRef} className="w-full h-full" />

      {/* Top Left Controls Stack: Fit Area & Fallback Notice (cleanly stacked vertically without overlap) */}
      <div className="absolute top-3 left-3 z-10 flex flex-col items-start gap-1.5 pointer-events-auto">
        <button
          onClick={fitToFeatures}
          className="flex items-center gap-1.5 px-2.5 py-1 bg-[#121821]/90 backdrop-blur-md border border-[#162733] hover:border-[#1e3448] text-[#8b98a9] hover:text-[#e6edf3] text-[11px] font-semibold rounded shadow transition-colors"
          title="Fit map to active features"
          aria-label="Fit view to active fire features"
        >
          <span aria-hidden="true">⛶</span>
          <span>Fit Area</span>
        </button>

        {isUsingFallback && (
          <div
            className="flex items-center gap-1.5 px-2 py-1 bg-[#121821]/95 backdrop-blur-md border border-[#f5a524]/50 text-[#f5a524] text-[10px] rounded shadow-lg font-mono"
            role="status"
            aria-live="polite"
          >
            <span className="w-1.5 h-1.5 rounded-full bg-[#f5a524] animate-pulse" aria-hidden="true" />
            <span>Fallback: OSM Standard</span>
          </div>
        )}
      </div>

      {/* Selected Settlement Highlight Banner (positioned to avoid top-left control stack) */}
      {selectedSettlementId && (
        <div className="absolute top-3 right-14 z-10 hidden sm:flex items-center gap-2 px-2.5 py-1 bg-[#121821]/90 backdrop-blur-md border border-[#ff6a2b]/40 rounded shadow text-xs">
          <span className="text-[#ff6a2b]">⬡</span>
          <span className="text-[#e6edf3] font-medium">
            {settlements.find((s) => s.id === selectedSettlementId)?.name || 'Selected Settlement'}
          </span>
          <span className="text-[10px] text-[#8b98a9] font-mono">
            {formatArrivalHours(settlements.find((s) => s.id === selectedSettlementId)?.fire_arrival_h)}
          </span>
          <button
            onClick={() => onSelectSettlement?.(null)}
            className="text-[#8b98a9] hover:text-[#e6edf3] ml-1"
            aria-label="Clear selection"
          >
            ✕
          </button>
        </div>
      )}
    </div>
  );
}
