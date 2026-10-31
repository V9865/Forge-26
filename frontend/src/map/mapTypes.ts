/**
 * EmberRoute — Map types and layer definitions
 */

import type {
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
}
