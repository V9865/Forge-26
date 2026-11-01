/**
 * MapView — MapLibre GL JS lifecycle and layer management component.
 */

import { useEffect, useRef, useState } from 'react';
import {
  Map,
  NavigationControl,
  Popup,
  Marker,
  LngLatBounds,
  type MapMouseEvent,
  type GeoJSONSource,
  type ErrorEvent,
} from 'maplibre-gl';
import { createBaseMapStyle, OSM_FALLBACK_TILES, OSM_ATTRIBUTION } from './mapLayers';
import { createSettlementPopupNode, createDetectionPopupNode } from './mapPopups';
import type { MapDataProps, MapLayerVisibility } from './mapTypes';
import { formatArrivalMinutes } from '@/utils/format';

interface MapViewProps extends MapDataProps {
  visibility: MapLayerVisibility;
  timeFilterHours: number;
}

export function MapView({
  detections = null,
  arrivalBands = null,
  settlements = null,
  routes = null,
  naiveCutSegments = null,
  selectedSettlementId,
  onSelectSettlement,
  scenarioIgnition,
  onSelectIgnition,
  isScenarioMode = false,
  focusAoi = null,
  onBoundsChange,
  flyToTarget = null,
  visibility,
  timeFilterHours,
}: MapViewProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<Map | null>(null);
  const popupRef = useRef<Popup | null>(null);
  const hasSwitchedToFallbackRef = useRef(false);
  const onBoundsChangeRef = useRef(onBoundsChange);
  useEffect(() => {
    onBoundsChangeRef.current = onBoundsChange;
  }, [onBoundsChange]);

  const [mapLoaded, setMapLoaded] = useState(false);
  const [isUsingFallback, setIsUsingFallback] = useState(false);
  const scenarioMarkerRef = useRef<Marker | null>(null);

  // Dedicated High-Visibility DOM Marker for Scenario Ignition
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapLoaded) return;

    if (scenarioIgnition) {
      const popupHtml = `
        <div style="font-family: inherit; font-size: 11px; padding: 6px 8px; color: #fff; background: #121821; border-radius: 6px; border: 1.5px solid #ff6a2b; box-shadow: 0 4px 16px rgba(0,0,0,0.6);">
          <strong style="color: #ff6a2b; display: flex; align-items: center; gap: 4px;">🔥 Scenario Ignition Point</strong>
          <div style="font-family: monospace; font-size: 10px; color: #e6edf3; margin-top: 3px;">
            ${scenarioIgnition.lat.toFixed(4)}°N, ${scenarioIgnition.lng.toFixed(4)}°E
          </div>
        </div>
      `;

      if (!scenarioMarkerRef.current) {
        const el = document.createElement('div');
        el.className = 'ember-scenario-ignition-marker';
        el.style.cssText =
          'width: 48px; height: 48px; display: flex; align-items: center; justify-content: center; cursor: pointer; pointer-events: auto;';
        el.innerHTML = `
          <div style="position: absolute; width: 44px; height: 44px; border-radius: 50%; background: rgba(255, 106, 43, 0.45); animation: ping 1.5s cubic-bezier(0, 0, 0.2, 1) infinite;"></div>
          <div style="position: relative; width: 30px; height: 30px; border-radius: 50%; background: #ff6a2b; border: 2.5px solid #ffffff; box-shadow: 0 0 16px rgba(255, 106, 43, 0.95); display: flex; align-items: center; justify-content: center; font-size: 15px; user-select: none;">🔥</div>
        `;
        const marker = new Marker({ element: el, anchor: 'center' })
          .setLngLat([scenarioIgnition.lng, scenarioIgnition.lat])
          .setPopup(new Popup({ offset: 20 }).setHTML(popupHtml))
          .addTo(map);
        scenarioMarkerRef.current = marker;
      } else {
        scenarioMarkerRef.current.setLngLat([scenarioIgnition.lng, scenarioIgnition.lat]);
        scenarioMarkerRef.current.getPopup()?.setHTML(popupHtml);
      }
    } else {
      if (scenarioMarkerRef.current) {
        scenarioMarkerRef.current.remove();
        scenarioMarkerRef.current = null;
      }
    }
  }, [mapLoaded, scenarioIgnition]);

  useEffect(() => {
    return () => {
      if (scenarioMarkerRef.current) {
        scenarioMarkerRef.current.remove();
        scenarioMarkerRef.current = null;
      }
    };
  }, []);

  // Update canvas cursor whenever scenario mode changes
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapLoaded) return;
    map.getCanvas().style.cursor = isScenarioMode ? 'crosshair' : '';
  }, [isScenarioMode, mapLoaded]);

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

    const emitBounds = () => {
      if (!mapRef.current || !onBoundsChangeRef.current) return;
      const b = mapRef.current.getBounds();
      onBoundsChangeRef.current({
        west: Number(b.getWest().toFixed(4)),
        south: Number(b.getSouth().toFixed(4)),
        east: Number(b.getEast().toFixed(4)),
        north: Number(b.getNorth().toFixed(4)),
      });
    };

    map.on('load', () => {
      setMapLoaded(true);
      emitBounds();
    });

    map.on('moveend', emitBounds);

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
          const style = map.getStyle();
          if (style && style.sources && style.sources['basemap']) {
            map.setStyle(createBaseMapStyle(true));
            setIsUsingFallback(true);
          }
        } catch {
          // If style update fails, attempt direct tile update
          try {
            const source = map.getSource('basemap') as any;
            if (source && typeof source.setTiles === 'function') {
              source.setTiles(OSM_FALLBACK_TILES);
              source.attribution = OSM_ATTRIBUTION;
              setIsUsingFallback(true);
            }
          } catch {
            // Soft failure, preserve current state
          }
        }
      }
    });

    // Handle container resizing (e.g. sidebar toggle or panel collapse)
    const resizeObserver = new ResizeObserver(() => {
      map.resize();
    });
    resizeObserver.observe(containerRef.current);

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
        .setDOMContent(createSettlementPopupNode(props))
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
        .setDOMContent(createDetectionPopupNode(coords, props))
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
      try {
        const queryLayers = ['settlements-circle', 'fire-detections-point', 'fire-detections-clusters'].filter(
          (id) => Boolean(map.getLayer(id)),
        );
        if (queryLayers.length > 0) {
          const interactiveFeatures = map.queryRenderedFeatures(e.point, { layers: queryLayers });
          if (interactiveFeatures.length > 0) return;
        }
      } catch {
        // Safe fallback
      }

      if (!onSelectIgnition) return;

      onSelectIgnition({
        lat: Number(e.lngLat.lat.toFixed(5)),
        lng: Number(e.lngLat.lng.toFixed(5)),
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

    // A. Fire detections source (Real GeoJSON FeatureCollection directly)
    const detectionsSource = map.getSource('fire-detections') as GeoJSONSource | undefined;
    if (detectionsSource) {
      detectionsSource.setData(
        detections ?? { type: 'FeatureCollection', features: [] },
      );
    }

    // B. Arrival bands source — Wavefront progressive revelation (0 to 12 hours)
    const arrivalSource = map.getSource('arrival-bands') as GeoJSONSource | undefined;
    if (arrivalSource) {
      const maxMinutes = timeFilterHours * 60;
      const rawFeatures = arrivalBands?.features ?? [];
      const sortedFeatures = [...rawFeatures].sort((a, b) => {
        const tA = (a.properties?.t_min as number) ?? 0;
        const tB = (b.properties?.t_min as number) ?? 0;
        return tB - tA;
      });

      const filteredFeatures = sortedFeatures.filter((f) => {
        const tMin = (f.properties?.t_min as number) ?? 0;
        return tMin <= maxMinutes;
      });

      arrivalSource.setData({
        type: 'FeatureCollection',
        features: filteredFeatures,
      });
    }

    // C. Settlements source with isSelected property injection
    const settlementsSource = map.getSource('settlements') as GeoJSONSource | undefined;
    if (settlementsSource) {
      const rawSettlements = settlements?.features ?? [];
      const updatedFeatures = rawSettlements.map((s) => ({
        ...s,
        properties: {
          ...s.properties,
          isSelected: s.properties?.id === selectedSettlementId,
        },
      }));

      settlementsSource.setData({
        type: 'FeatureCollection',
        features: updatedFeatures,
      });
    }

    // D. Safe evacuation routes (result.routes FeatureCollection)
    const routesSource = map.getSource('evacuation-routes') as GeoJSONSource | undefined;
    if (routesSource) {
      routesSource.setData(
        routes ?? { type: 'FeatureCollection', features: [] },
      );
    }

    // E. Naive baseline routes cut by fire (result.naive_cut_segments FeatureCollection)
    const baselineSource = map.getSource('baseline-routes') as GeoJSONSource | undefined;
    if (baselineSource) {
      baselineSource.setData(
        naiveCutSegments ?? { type: 'FeatureCollection', features: [] },
      );
    }

    // F. Scenario ignition point
    const ignitionSource = map.getSource('scenario-ignition') as GeoJSONSource | undefined;
    if (ignitionSource) {
      const features: GeoJSON.Feature<GeoJSON.Point>[] =
        scenarioIgnition
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
    naiveCutSegments,
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
    setVisibility(
      ['evacuation-routes-line', 'evacuation-routes-glow', 'evacuation-routes-casing'].filter((id) => Boolean(map.getLayer(id))),
      visibility.routes,
    );
    setVisibility(
      ['baseline-routes-line', 'baseline-routes-casing'].filter((id) => Boolean(map.getLayer(id))),
      visibility.baselineRoutes,
    );

    // Scenario beacon layer visibility
    setVisibility(
      ['scenario-ignition-point', 'scenario-ignition-pulse'],
      Boolean(scenarioIgnition),
    );
  }, [mapLoaded, visibility, scenarioIgnition]);

  // ── 4b. Focus AOI ─────────────────────────────────────────────────────────
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapLoaded || !focusAoi) return;
    try {
      const b = new LngLatBounds(
        [focusAoi.west, focusAoi.south],
        [focusAoi.east, focusAoi.north],
      );
      map.fitBounds(b, { padding: 48, maxZoom: 13, duration: 900 });
    } catch {
      // Ignored if bounds invalid
    }
  }, [focusAoi, mapLoaded]);

  // ── 4c. Fly To Target (Coordinate button clicks, Presets, Clusters, Settlements) ─
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapLoaded || !flyToTarget) return;

    map.flyTo({
      center: flyToTarget.center,
      zoom: flyToTarget.zoom ?? 11,
      pitch: flyToTarget.pitch ?? 0,
      bearing: flyToTarget.bearing ?? 0,
      speed: 1.6,
      curve: 1.4,
      essential: true,
    });
  }, [flyToTarget, mapLoaded]);

  // ── 4d. Selected Settlement Map Sync (Auto-Popup) ───────────────────────────
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapLoaded || !selectedSettlementId || !settlements?.features) return;

    const feature = settlements.features.find((f) => f.properties?.id === selectedSettlementId);
    if (!feature || feature.geometry.type !== 'Point') return;

    const coords = feature.geometry.coordinates as [number, number];
    popupRef.current?.remove();
    const popup = new Popup({ offset: 12, className: 'ember-map-popup' })
      .setLngLat(coords)
      .setDOMContent(createSettlementPopupNode(feature.properties))
      .addTo(map);

    popupRef.current = popup;
  }, [selectedSettlementId, settlements, mapLoaded]);

  // ── 5. Auto Fit-to-Bounds helper ───────────────────────────────────────────
  const fitToFeatures = () => {
    const map = mapRef.current;
    if (!map) return;

    const coords: [number, number][] = [];

    // Safely extract coordinates from GeoJSON FeatureCollections
    detections?.features?.forEach((f) => {
      if (f.geometry?.type === 'Point' && Array.isArray(f.geometry.coordinates)) {
        coords.push(f.geometry.coordinates as [number, number]);
      }
    });

    settlements?.features?.forEach((s) => {
      if (s.geometry?.type === 'Point' && Array.isArray(s.geometry.coordinates)) {
        coords.push(s.geometry.coordinates as [number, number]);
      }
    });

    if (scenarioIgnition) {
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

  const selectedSettlementFeature = settlements?.features?.find(
    (s) => s.properties?.id === selectedSettlementId,
  );

  return (
    <div className="relative w-full h-full min-h-0 min-w-0">
      <div ref={containerRef} className="w-full h-full" />

      {/* Top Left Controls Stack: Fit Area & Fallback Notice */}
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

      {/* Selected Settlement Highlight Banner */}
      {selectedSettlementId && (
        <div className="absolute top-3 right-14 z-10 hidden sm:flex items-center gap-2 px-2.5 py-1 bg-[#121821]/90 backdrop-blur-md border border-[#ff6a2b]/40 rounded shadow text-xs">
          <span className="text-[#ff6a2b]">⬡</span>
          <span className="text-[#e6edf3] font-medium">
            {selectedSettlementFeature?.properties?.name || 'Selected Settlement'}
          </span>
          <span className="text-[10px] text-[#8b98a9] font-mono">
            {formatArrivalMinutes(selectedSettlementFeature?.properties?.fire_arrival_min)}
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
