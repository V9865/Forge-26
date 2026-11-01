/**

 * EmberRoute — Centralized TypeScript types

 *

 * Fully aligned with the frozen backend API contract in:

 * - api/schemas.py

 * - api/main.py

 * - api/jobs.py

 * - api/geojson.py

 */



import type {

  FeatureCollection,

  LineString,

  MultiPolygon,

  Point,

  Polygon,

} from 'geojson';



// ─── Operating modes & Parameters ─────────────────────────────────────────────



export type OperatingMode = 'LIVE' | 'SCENARIO';



export type SimulationResolution = 60 | 90 | 120;



export type ResolutionM = SimulationResolution;



// ─── Evacuation status ────────────────────────────────────────────────────────



export type SettlementStatus =

  | 'NOT_THREATENED'

  | 'EVACUATE'

  | 'TRAPPED'

  | 'ALREADY_BURNING';



export type EvacuationStatus = SettlementStatus | 'DEPART_SOON';



// ─── Geographic & Physical Spec Models ────────────────────────────────────────



export interface AOIModel {

  west: number;

  south: number;

  east: number;

  north: number;

}



export interface IgnitionPoint {

  lat: number;

  lon: number;

}



export interface WindOverrideModel {

  speed_ms?: number | null;

  dir_from_deg?: number | null;

}



export interface GridModel {

  res_m: number;

  nx: number;

  ny: number;

}



// ─── Meteorological Data Models ───────────────────────────────────────────────



export interface WindNowModel {

  speed_ms: number;

  dir_from_deg: number;

  rh: number;

}



export interface WindPointModel {

  t_utc: string;

  speed_ms: number;

  dir_from_deg: number;

  rh: number;

}



export interface WindModel {

  source: string;

  is_override: boolean;

  is_stale: boolean;

  fetched_at_utc: string;

  now: WindNowModel;

  series: WindPointModel[];

}



// ─── Briefing, Provenance & Trace Models ──────────────────────────────────────



export interface BriefingModel {

  text: string;

  used_llm: boolean;

  provider?: string | null;

  model?: string | null;

  dropped_sentences: number;

  facts: Record<string, string>;

}



export interface ProvenanceModel {

  name: string;

  source: string;

  url?: string | null;

  fetched_at_utc: string;

  age_s?: number | null;

  ttl_s: number;

  is_stale: boolean;

  note?: string | null;

}



export interface TraceStepModel {

  ts_utc: string;

  step: string;

  tool?: string | null;

  status: string;

  duration_ms: number;

  note?: string | null;

}



// Alias for backwards compatibility

export type TraceEntry = TraceStepModel;



// ─── GeoJSON Layer Feature Properties ─────────────────────────────────────────



export interface FireDetectionProperties {

  acq_time_utc: string;

  frp: number;

  confidence: number | string;

  satellite: string;

  [key: string]: unknown;

}



export interface ArrivalBandProperties {

  t_min: number;

  [key: string]: unknown;

}



export interface SettlementProperties {

  id: string;

  name: string;

  status: SettlementStatus;

  fire_arrival_min: number | null;

  depart_by_min: number | null;

  route_travel_min: number | null;

  naive_cut: boolean;

  note?: string | null;

  isSelected?: boolean;

  [key: string]: unknown;

}



export interface RouteProperties {

  settlement_id: string;

  kind?: string;

  cut?: boolean;

  [key: string]: unknown;

}



export interface CutSegmentProperties {

  settlement_id: string;

  [key: string]: unknown;

}



// ─── Typed GeoJSON Feature Collections ────────────────────────────────────────



export type DetectionsFeatureCollection = FeatureCollection<Point, FireDetectionProperties>;



export type ArrivalBandsFeatureCollection = FeatureCollection<Polygon | MultiPolygon, ArrivalBandProperties>;



export type SettlementsFeatureCollection = FeatureCollection<Point, SettlementProperties>;



export type RoutesFeatureCollection = FeatureCollection<LineString, RouteProperties>;



export type CutSegmentsFeatureCollection = FeatureCollection<LineString, CutSegmentProperties>;



// ─── Simulation Plan Result ───────────────────────────────────────────────────



export interface PlanResult {

  mode: OperatingMode;

  aoi: AOIModel;

  grid: GridModel;

  wind: WindModel;

  detections: DetectionsFeatureCollection;

  arrival_bands?: ArrivalBandsFeatureCollection | null;

  settlements?: SettlementsFeatureCollection | null;

  routes?: RoutesFeatureCollection | null;

  naive_cut_segments?: CutSegmentsFeatureCollection | null;
  roads?: GeoJSON.FeatureCollection | null;

  metrics: Record<string, unknown>;

  briefing?: BriefingModel | null;

  provenance: ProvenanceModel[];

  warnings: string[];

  trace: TraceStepModel[];

}



// Alias for backwards compatibility

export type JobResult = PlanResult;



// ─── API: Plan Request & Response ─────────────────────────────────────────────



export interface PlanRequest {

  aoi: AOIModel;

  mode?: OperatingMode;

  ignition?: IgnitionPoint | null;

  wind_override?: WindOverrideModel | null;

  resolution_m?: ResolutionM;

}



export interface PlanJobResponse {

  job_id: string;

}



// Alias for backwards compatibility

export type PlanResponse = PlanJobResponse;



// ─── API: Job Polling ─────────────────────────────────────────────────────────



export type JobStatus = 'queued' | 'running' | 'done' | 'error';



export interface JobStatusResponse {

  job_id: string;

  status: JobStatus;

  stage?: string | null;

  progress: number; // 0.0 to 1.0 from backend

  trace: TraceStepModel[];

  result?: PlanResult | null;

  error?: ErrorDetail | null;

}



// Alias for backwards compatibility

export type JobPollResponse = JobStatusResponse;



// ─── API: Clusters ────────────────────────────────────────────────────────────



export interface ClusterItem {

  id: string;

  name?: string | null;

  lat: number;

  lon: number;

  count: int;

  total_frp: number;

  suggested_aoi: AOIModel;

}



type int = number;



// ─── API: Health Diagnostics ──────────────────────────────────────────────────



export interface FeedHealthDetail {

  ok: boolean;

  latency_ms: number;

  detail: string;

  checked_at: string;

}



export interface HealthResponse {

  feeds: Record<string, FeedHealthDetail>;

}



// ─── API: Monitor ─────────────────────────────────────────────────────────────



export interface MonitorRequest {

  enabled: boolean;

  aoi?: AOIModel | null;

  mode?: OperatingMode;

  ignition?: IgnitionPoint | null;

  wind_override?: WindOverrideModel | null;

  poll_s?: number;

}



export interface MonitorStatusResponse {

  enabled: boolean;

  last_cycle_utc?: string | null;

  last_reasons: string[];

  current_job_id?: string | null;

  next_poll_utc?: string | null;

}



// Alias for backwards compatibility

export type MonitorStatus = MonitorStatusResponse;



// ─── API: Assumptions & Validation ────────────────────────────────────────────



export interface AssumptionsResponse {

  text: string;

}



export interface ValidationEvent {

  event: string;

  split: string;

  grid: string;

  future_detections: number;

  model_recall: number;

  baseline_recall: number;

  predicted_area_ha: number;

  bearing_error_deg: number;

}



export interface ValidationParameters {

  k_wind?: number;

  midflame?: number;

  ros_scale?: number;

  lb_cap?: number;

  [key: string]: unknown;

}



export interface ValidationSummary {

  held_out_test_recall?: number;

  baseline_recall?: number;

  performance_margin?: string;

  [key: string]: unknown;

}



export interface ValidationResponse {

  available: boolean;

  events: ValidationEvent[];

  parameters: ValidationParameters;

  summary: ValidationSummary;

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

  | 'TIMEOUT'

  | 'RATE_LIMITED';



export interface ErrorDetail {

  code: string;

  message: string;

}



// Alias for backwards compatibility

export type ApiError = ErrorDetail;



export interface ErrorResponse {

  error: ErrorDetail;

}



// Alias for backwards compatibility

export type ApiErrorResponse = ErrorResponse;



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

