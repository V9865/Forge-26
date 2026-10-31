/**
 * EmberRoute — Centralized TypeScript types
 *
 * These types define the agreed API contract.
 * Nested field structures for `aoi`, `ignition`, and `wind_override`
 * are marked as `unknown` pending OpenAPI confirmation.
 * Do NOT manually edit generated sections once OpenAPI types are available.
 */

import type {
  Geometry,
  LineString,
  MultiLineString,
} from 'geojson';

// ─── Operating modes ──────────────────────────────────────────────────────────

export type OperatingMode = 'LIVE' | 'SCENARIO';

export type SimulationResolution = 60 | 90 | 120;

// ─── Data freshness / quality ─────────────────────────────────────────────────

export type DataQuality = 'LIVE' | 'SCENARIO' | 'STALE' | 'DEGRADED' | 'UNAVAILABLE';

// ─── Evacuation status ────────────────────────────────────────────────────────

export type EvacuationStatus =
  | 'EVACUATE'
  | 'DEPART_SOON'
  | 'TRAPPED'
  | 'ALREADY_BURNING'
  | 'NOT_THREATENED';

// ─── API: Health ──────────────────────────────────────────────────────────────

export interface HealthResponse {
  status: string;
  version?: string;
  timestamp?: string;
}

// ─── API: Fire clusters ───────────────────────────────────────────────────────

export interface FireCluster {
  /** Unique cluster identifier */
  id: string;
  /** Human-readable label or name */
  label?: string;
  /** Number of fire detections in this cluster */
  detection_count: number;
  /** Cluster centroid [longitude, latitude] */
  centroid: [number, number];
  /** Bounding box [west, south, east, north] */
  bbox?: [number, number, number, number];
  /** Detection timestamps span */
  first_detected?: string;
  last_detected?: string;
  /** Source satellite/sensor */
  source?: string;
}

export interface ClustersResponse {
  clusters: FireCluster[];
  feed_freshness?: string;
  feed_status?: 'OK' | 'STALE' | 'DOWN';
  hours_requested?: number;
}

// ─── API: Plan request ────────────────────────────────────────────────────────

/**
 * Area of interest.
 * Exact nested structure to be confirmed from OpenAPI.
 */
export type AoiInput = Record<string, unknown>;

/**
 * Ignition point for SCENARIO mode.
 * Exact nested structure to be confirmed from OpenAPI.
 */
export type IgnitionInput = Record<string, unknown>;

/**
 * Wind override parameters.
 * Exact nested structure to be confirmed from OpenAPI.
 */
export type WindOverrideInput = Record<string, unknown>;

export interface PlanRequest {
  aoi: AoiInput;
  mode: OperatingMode;
  ignition?: IgnitionInput;
  wind_override?: WindOverrideInput;
  resolution_m: SimulationResolution;
}

export interface PlanResponse {
  job_id: string;
}

// ─── API: Job polling ─────────────────────────────────────────────────────────

export type JobStatus = 'PENDING' | 'RUNNING' | 'DONE' | 'ERROR';

export interface TraceEntry {
  timestamp: string;
  stage: string;
  message: string;
  level?: 'INFO' | 'WARN' | 'ERROR';
}

export interface ArrivalBand {
  /** Hours from now */
  hours_min: number;
  hours_max: number;
  /** GeoJSON geometry */
  geometry: Geometry;
}

export interface Settlement {
  id: string;
  name: string;
  coordinates: [number, number];
  status: EvacuationStatus;
  /** Estimated fire arrival in hours */
  fire_arrival_h?: number;
  /** ISO timestamp of latest safe departure */
  depart_by?: string;
  /** ID of recommended evacuation route */
  route_id?: string;
  warnings?: string[];
}

export interface EvacuationRoute {
  id: string;
  settlement_id: string;
  geometry: LineString | MultiLineString;
  is_fire_aware: boolean;
  /** Whether this is the fire-blind naive baseline */
  is_baseline?: boolean;
  distance_km?: number;
  duration_min?: number;
  cut_segments?: number;
  cut_reason?: string;
}

export interface JobResult {
  /** v0 */
  mode?: OperatingMode;
  aoi?: AoiInput;
  grid?: Record<string, unknown>;
  wind?: WindInfo;
  detections?: FireDetection[];
  provenance?: ProvenanceInfo[];
  warnings?: string[];

  /** v1 */
  arrival_bands?: ArrivalBand[];
  burned_area_km2?: number;

  /** v2 */
  settlements?: Settlement[];
  routes?: EvacuationRoute[];
  naive_cut_segments?: number;
  evacuation_metrics?: EvacuationMetrics;

  /** v3 */
  briefing?: string | BriefingStructured;
}

export interface JobPollResponse {
  job_id: string;
  status: JobStatus;
  stage?: string;
  progress?: number;
  trace?: TraceEntry[];
  result?: JobResult;
  error?: ApiError;
}

// ─── Supporting data types ────────────────────────────────────────────────────

export interface FireDetection {
  latitude: number;
  longitude: number;
  timestamp?: string;
  satellite?: string;
  confidence?: number | 'low' | 'nominal' | 'high';
  brightness?: number;
  source?: string;
}

export interface WindInfo {
  speed_ms?: number;
  direction_deg?: number;
  source?: string;
  timestamp?: string;
  is_override?: boolean;
}

export interface ProvenanceInfo {
  source: string;
  url?: string;
  description?: string;
  freshness?: string;
  status?: 'OK' | 'STALE' | 'DOWN';
}

export interface EvacuationMetrics {
  settlements_total?: number;
  settlements_threatened?: number;
  settlements_trapped?: number;
  routes_available?: number;
  time_to_first_threat_h?: number;
}

export interface BriefingStructured {
  summary?: string;
  threat_assessment?: string;
  recommended_actions?: string[];
  caveats?: string[];
}

// ─── API: Monitor ─────────────────────────────────────────────────────────────

export interface MonitorRequest {
  enabled: boolean;
  aoi?: AoiInput;
  mode?: OperatingMode;
  ignition?: IgnitionInput;
  wind_override?: WindOverrideInput;
  poll_s?: number;
}

export interface MonitorStatus {
  enabled: boolean;
  last_check?: string;
  next_check?: string;
  changes_detected?: string[];
  replanning_triggered?: boolean;
  current_job_id?: string;
}

// ─── API: Assumptions ────────────────────────────────────────────────────────

export interface AssumptionsResponse {
  model_type?: string;
  limitations?: string[];
  data_sources?: ProvenanceInfo[];
  notes?: string[];
}

// ─── API: Validation ─────────────────────────────────────────────────────────

export interface ValidationMetric {
  name: string;
  value: number | string;
  unit?: string;
  description?: string;
}

export interface ValidationResponse {
  metrics?: ValidationMetric[];
  notes?: string[];
  last_validated?: string;
}

// ─── API: Errors ──────────────────────────────────────────────────────────────

export type ApiErrorCode =
  | 'NO_FIRE'
  | 'FEED_DOWN'
  | 'OSM_EMPTY'
  | 'GRID_TOO_LARGE'
  | 'NO_SETTLEMENTS'
  | 'BAD_INPUT'
  | 'NEEDS_SCENARIO'
  | 'INTERNAL'
  | 'NETWORK_ERROR'
  | 'TIMEOUT';

export interface ApiError {
  code: ApiErrorCode | string;
  message: string;
}

export interface ApiErrorResponse {
  error: ApiError;
}

// ─── App state ────────────────────────────────────────────────────────────────

export type ConnectionStatus = 'CONNECTED' | 'CONNECTING' | 'DISCONNECTED' | 'ERROR';

export interface AppState {
  connectionStatus: ConnectionStatus;
  operatingMode: OperatingMode;
  selectedClusterId: string | null;
  selectedSettlementId: string | null;
  currentJobId: string | null;
  jobStatus: JobStatus | null;
  isMonitoringEnabled: boolean;
}
