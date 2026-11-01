/**
 * MapView — Core MapLibre GL JS map engine with OpenFreeMap vector basemap integration.
 *
 * Implements:
 * - OpenFreeMap dark vector tiles (default: https://tiles.openfreemap.org/styles/dark)
 * - Dynamic GeoJSON source synchronization (detections, wavefronts, settlements, routes, wind)
 * - AWS Terrarium DEM hillshade overlay
 * - Scenario ignition beacon and responsive interactions
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
import type { Feature, Point } from 'geojson';
import {
  setupOperationalLayers,
  DEFAULT_OPENFREEMAP_STYLE,
  createFallbackRasterStyle,
  SOURCES,
  LAYERS,
  DEFAULT_MAP_CENTER,
  DEFAULT_MAP_ZOOM,
} from './mapLayers';
import { updateGeoJsonSource } from './sources/geoJsonSources';
import { sanitizeFeatureCollection, emptyFeatureCollection } from './utils/geoJsonValidation';
import { spreadBearingFromWindDir, cardinalFromDegrees } from './utils/coordinateUtils';
import { createSettlementPopupNode, createDetectionPopupNode } from './mapPopups';
import type { MapDataProps, MapLayerVisibility } from './mapTypes';

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
  windData = null,
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
  const scenarioMarkerRef = useRef<Marker | null>(null);
  const hasFallbackTriggeredRef = useRef(false);

  const [mapLoaded, setMapLoaded] = useState(false);

  const onBoundsChangeRef = useRef(onBoundsChange);
  useEffect(() => {
    onBoundsChangeRef.current = onBoundsChange;
  }, [onBoundsChange]);

  // ── 1. Map Initialization (Single-Instance Lifecycle) ──────────────────────
  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;

    const map = new Map({
      container: containerRef.current,
      style: DEFAULT_OPENFREEMAP_STYLE,
      center: DEFAULT_MAP_CENTER,
      zoom: DEFAULT_MAP_ZOOM,
      pitch: 0,
      bearing: 0,
      attributionControl: { compact: true },
    });

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
      setupOperationalLayers(map);
      setMapLoaded(true);
      emitBounds();
    });

    map.on('moveend', emitBounds);

    // Resilient Fallback: If OpenFreeMap style fails (e.g. offline/blocked), fallback to raster style
    map.on('error', (e: ErrorEvent) => {
      const isStyleError =
        e.error &&
        (e.error.message.includes('openfreemap') ||
          e.error.message.includes('styles/dark') ||
          e.error.message.includes('Failed to fetch'));

      if (isStyleError && !hasFallbackTriggeredRef.current && !mapLoaded) {
        hasFallbackTriggeredRef.current = true;
        console.warn('[EmberRoute Map] OpenFreeMap style unavailable, switching to fallback raster style');
        try {
          map.setStyle(createFallbackRasterStyle());
        } catch {
          // Soft failure
        }
      }
    });

    const resizeObserver = new ResizeObserver(() => {
      map.resize();
    });
    resizeObserver.observe(containerRef.current);

    mapRef.current = map;

    return () => {
      resizeObserver.disconnect();
      popupRef.current?.remove();
      scenarioMarkerRef.current?.remove();
      map.remove();
      mapRef.current = null;
      setMapLoaded(false);
    };
  }, []); // Run ONCE on mount

  // ── 2. Scenario Ignition DOM Marker ────────────────────────────────────────
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
          'width: 44px; height: 44px; display: flex; align-items: center; justify-content: center; cursor: pointer; pointer-events: auto;';
        el.innerHTML = `
          <div style="position: absolute; width: 40px; height: 40px; border-radius: 50%; background: rgba(255, 106, 43, 0.45); animation: ping 1.5s cubic-bezier(0, 0, 0.2, 1) infinite;"></div>
          <div style="position: relative; width: 28px; height: 28px; border-radius: 50%; background: #ff6a2b; border: 2.5px solid #ffffff; box-shadow: 0 0 16px rgba(255, 106, 43, 0.95); display: flex; align-items: center; justify-content: center; font-size: 14px; user-select: none;">🔥</div>
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

  // Update canvas cursor in scenario mode
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapLoaded) return;
    map.getCanvas().style.cursor = isScenarioMode ? 'crosshair' : '';
  }, [isScenarioMode, mapLoaded]);

  // ── 3. Interactions & Popups ───────────────────────────────────────────────
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapLoaded) return;

    // Click on settlements
    const handleSettlementClick = (e: MapMouseEvent) => {
      const features = map.queryRenderedFeatures(e.point, { layers: [LAYERS.SETTLEMENTS_CIRCLE] });
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
      const features = map.queryRenderedFeatures(e.point, { layers: [LAYERS.DETECTIONS_POINT] });
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

    // Click on fire clusters
    const handleClusterClick = (e: MapMouseEvent) => {
      const features = map.queryRenderedFeatures(e.point, { layers: [LAYERS.DETECTIONS_CLUSTERS] });
      if (!features.length) return;

      const clusterId = features[0].properties?.cluster_id;
      const source = map.getSource(SOURCES.DETECTIONS) as GeoJSONSource | undefined;
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
        const queryLayers = [
          LAYERS.SETTLEMENTS_CIRCLE,
          LAYERS.DETECTIONS_POINT,
          LAYERS.DETECTIONS_CLUSTERS,
        ].filter((id) => Boolean(map.getLayer(id)));
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

    const setPointer = () => {
      map.getCanvas().style.cursor = 'pointer';
    };
    const resetPointer = () => {
      map.getCanvas().style.cursor = isScenarioMode ? 'crosshair' : '';
    };

    map.on('click', LAYERS.SETTLEMENTS_CIRCLE, handleSettlementClick);
    map.on('click', LAYERS.DETECTIONS_POINT, handleDetectionClick);
    map.on('click', LAYERS.DETECTIONS_CLUSTERS, handleClusterClick);
    map.on('click', handleMapClick);

    map.on('mouseenter', LAYERS.SETTLEMENTS_CIRCLE, setPointer);
    map.on('mouseleave', LAYERS.SETTLEMENTS_CIRCLE, resetPointer);
    map.on('mouseenter', LAYERS.DETECTIONS_POINT, setPointer);
    map.on('mouseleave', LAYERS.DETECTIONS_POINT, resetPointer);
    map.on('mouseenter', LAYERS.DETECTIONS_CLUSTERS, setPointer);
    map.on('mouseleave', LAYERS.DETECTIONS_CLUSTERS, resetPointer);

    return () => {
      map.off('click', LAYERS.SETTLEMENTS_CIRCLE, handleSettlementClick);
      map.off('click', LAYERS.DETECTIONS_POINT, handleDetectionClick);
      map.off('click', LAYERS.DETECTIONS_CLUSTERS, handleClusterClick);
      map.off('click', handleMapClick);

      map.off('mouseenter', LAYERS.SETTLEMENTS_CIRCLE, setPointer);
      map.off('mouseleave', LAYERS.SETTLEMENTS_CIRCLE, resetPointer);
      map.off('mouseenter', LAYERS.DETECTIONS_POINT, setPointer);
      map.off('mouseleave', LAYERS.DETECTIONS_POINT, resetPointer);
      map.off('mouseenter', LAYERS.DETECTIONS_CLUSTERS, setPointer);
      map.off('mouseleave', LAYERS.DETECTIONS_CLUSTERS, resetPointer);
    };
  }, [mapLoaded, onSelectSettlement, onSelectIgnition, isScenarioMode]);

  // ── 4. Dynamic GeoJSON Source Synchronization ──────────────────────────────
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapLoaded) return;

    // A. Fire Detections
    updateGeoJsonSource(map, SOURCES.DETECTIONS, sanitizeFeatureCollection(detections));

    // B. Arrival Bands with Progressive Time Slider Filtering
    const maxMinutes = timeFilterHours * 60;
    const rawArrivalFeatures = arrivalBands?.features ?? [];
    const sortedFeatures = [...rawArrivalFeatures].sort((a, b) => {
      const tA = (a.properties?.t_min as number) ?? 0;
      const tB = (b.properties?.t_min as number) ?? 0;
      return tB - tA; // Outer wavefront painted first, inner urgent wavefront on top
    });
    const filteredArrivalFeatures = sortedFeatures.filter((f) => {
      const tMin = (f.properties?.t_min as number) ?? 0;
      return tMin <= maxMinutes;
    });
    updateGeoJsonSource(map, SOURCES.ARRIVAL_BANDS, {
      type: 'FeatureCollection',
      features: filteredArrivalFeatures as any,
    });

    // C. Settlements
    const settlementFeatures = (settlements?.features ?? []).map((f) => ({
      ...f,
      properties: {
        ...f.properties,
        isSelected: f.properties?.id === selectedSettlementId,
      },
    }));
    updateGeoJsonSource(map, SOURCES.SETTLEMENTS, {
      type: 'FeatureCollection',
      features: settlementFeatures as any,
    });

    // D. Recommended Routes
    updateGeoJsonSource(map, SOURCES.ROUTES, sanitizeFeatureCollection(routes));

    // E. Naive Baseline Cut Segments
    updateGeoJsonSource(map, SOURCES.BASELINE_ROUTES, sanitizeFeatureCollection(naiveCutSegments));

    // F. Scenario Ignition Point
    const ignitionFeatures: Feature<Point>[] = scenarioIgnition
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
    updateGeoJsonSource(map, SOURCES.SCENARIO_IGNITION, {
      type: 'FeatureCollection',
      features: ignitionFeatures,
    });

    // G. Meteorological Wind Vector Overlay
    if (windData && (focusAoi || scenarioIgnition)) {
      const centerLon = focusAoi
        ? (focusAoi.west + focusAoi.east) / 2
        : scenarioIgnition!.lng;
      const centerLat = focusAoi
        ? (focusAoi.south + focusAoi.north) / 2
        : scenarioIgnition!.lat;

      const bearing = spreadBearingFromWindDir(windData.now.dir_from_deg);
      const cardinal = cardinalFromDegrees(windData.now.dir_from_deg);
      const windFeatures: Feature<Point>[] = [
        {
          type: 'Feature',
          properties: {
            bearing,
            label: `${windData.now.speed_ms.toFixed(1)} m/s (${cardinal})`,
          },
          geometry: {
            type: 'Point',
            coordinates: [centerLon, centerLat],
          },
        },
      ];
      updateGeoJsonSource(map, SOURCES.WIND, {
        type: 'FeatureCollection',
        features: windFeatures,
      });
    } else {
      updateGeoJsonSource(map, SOURCES.WIND, emptyFeatureCollection());
    }
  }, [
    mapLoaded,
    detections,
    arrivalBands,
    settlements,
    routes,
    naiveCutSegments,
    windData,
    selectedSettlementId,
    scenarioIgnition,
    focusAoi,
    timeFilterHours,
  ]);

  // ── 5. Layer Visibilities ──────────────────────────────────────────────────
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
      [
        LAYERS.DETECTIONS_CLUSTERS,
        LAYERS.DETECTIONS_CLUSTER_COUNT,
        LAYERS.DETECTIONS_POINT,
        LAYERS.DETECTIONS_POINT_GLOW,
      ],
      visibility.detections,
    );

    setVisibility(
      [LAYERS.ARRIVAL_BANDS_FILL, LAYERS.ARRIVAL_BANDS_STROKE],
      visibility.arrivalBands,
    );

    setVisibility(
      [LAYERS.SETTLEMENTS_CIRCLE, LAYERS.SETTLEMENTS_HALO, LAYERS.SETTLEMENTS_LABEL],
      visibility.settlements,
    );

    setVisibility(
      [
        LAYERS.EVACUATION_ROUTES_LINE,
        LAYERS.EVACUATION_ROUTES_GLOW,
        LAYERS.EVACUATION_ROUTES_CASING,
      ],
      visibility.routes,
    );

    setVisibility(
      [LAYERS.BASELINE_ROUTES_LINE, LAYERS.BASELINE_ROUTES_CASING],
      visibility.baselineRoutes,
    );

    setVisibility([LAYERS.WIND_ARROW, LAYERS.WIND_LABEL], visibility.wind);

    setVisibility([LAYERS.TERRAIN_HILLSHADE], visibility.terrain);

    setVisibility(
      [LAYERS.SCENARIO_POINT, LAYERS.SCENARIO_PULSE],
      Boolean(scenarioIgnition),
    );
  }, [mapLoaded, visibility, scenarioIgnition]);

  // ── 6. Focus AOI Camera Alignment ──────────────────────────────────────────
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapLoaded || !focusAoi) return;
    try {
      const b = new LngLatBounds(
        [focusAoi.west, focusAoi.south],
        [focusAoi.east, focusAoi.north],
      );
      map.fitBounds(b, { padding: 48, maxZoom: 13, duration: 800 });
    } catch {
      // Ignored if bounds invalid
    }
  }, [focusAoi, mapLoaded]);

  // ── 7. Fly To Target ───────────────────────────────────────────────────────
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

  // ── 8. Selected Settlement Auto-Popup ──────────────────────────────────────
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

  return (
    <div
      ref={containerRef}
      className="w-full h-full relative"
      tabIndex={0}
      aria-label="MapLibre OpenFreeMap interactive canvas"
    />
  );
}
