/**
 * EmberRoute — Map types and layer definitions
 */

import type {
  AOIModel,
  ArrivalBandsFeatureCollection,
  CutSegmentsFeatureCollection,
  DetectionsFeatureCollection,
  RoutesFeatureCollection,
  SettlementsFeatureCollection,
} from '@/types';

export interface MapLayerVisibility {
  detections: boolean;
  arrivalBands: boolean;
  settlements: boolean;
  routes: boolean;
  baselineRoutes: boolean;
}

export const DEFAULT_LAYER_VISIBILITY: MapLayerVisibility = {
  detections: true,
  arrivalBands: true,
  settlements: true,
  routes: true,
  baselineRoutes: true,
};

export interface FlyToTarget {
  center: [number, number]; // [lng, lat]
  zoom?: number;
  pitch?: number;
  bearing?: number;
  timestamp: number;
}

export interface MapDataProps {
  detections?: DetectionsFeatureCollection | null;
  arrivalBands?: ArrivalBandsFeatureCollection | null;
  settlements?: SettlementsFeatureCollection | null;
  routes?: RoutesFeatureCollection | null;
  naiveCutSegments?: CutSegmentsFeatureCollection | null;
  selectedSettlementId?: string | null;
  onSelectSettlement?: (settlementId: string | null) => void;
  // Scenario ignition point
  scenarioIgnition?: { lat: number; lng: number } | null;
  onSelectIgnition?: (point: { lat: number; lng: number }) => void;
  isScenarioMode?: boolean;
  // AOI focus & Viewport tracking
  focusAoi?: AOIModel | null;
  onBoundsChange?: (bounds: AOIModel) => void;
  flyToTarget?: FlyToTarget | null;
}
