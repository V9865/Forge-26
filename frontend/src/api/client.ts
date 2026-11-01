/**
 * EmberRoute — Centralized API client
 *
 * All backend communication is routed through this module.
 * Strictly aligned with the FastAPI backend contracts in api/main.py.
 */

import type {
  AssumptionsResponse,
  ClusterItem,
  ErrorResponse,
  HealthResponse,
  JobStatusResponse,
  MonitorRequest,
  MonitorStatusResponse,
  PlanJobResponse,
  PlanRequest,
  ValidationResponse,
} from '@/types';

// ─── Configuration ─────────────────────────────────────────────────────────────

const BASE_URL = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? '';
const DEFAULT_TIMEOUT_MS = 20_000;

// ─── Core fetch wrapper ────────────────────────────────────────────────────────

class ApiClientError extends Error {
  readonly code: string;
  readonly httpStatus: number | undefined;

  constructor(code: string, message: string, httpStatus?: number) {
    super(message);
    this.name = 'ApiClientError';
    this.code = code;
    this.httpStatus = httpStatus;
  }
}

async function apiFetch<T>(
  path: string,
  options: RequestInit = {},
  timeoutMs = DEFAULT_TIMEOUT_MS,
): Promise<T> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const response = await fetch(`${BASE_URL}${path}`, {
      ...options,
      signal: controller.signal,
      headers: {
        'Content-Type': 'application/json',
        Accept: 'application/json',
        ...options.headers,
      },
    });

    clearTimeout(timeoutId);

    if (!response.ok) {
      // Try to parse structured error from backend
      let errorBody: ErrorResponse | null = null;
      try {
        errorBody = (await response.json()) as ErrorResponse;
      } catch {
        // Ignore parse failure
      }

      const code = errorBody?.error?.code ?? (response.status === 429 ? 'RATE_LIMITED' : 'HTTP_ERROR');
      const message =
        errorBody?.error?.message ?? `HTTP ${response.status}: ${response.statusText}`;

      throw new ApiClientError(code, message, response.status);
    }

    return (await response.json()) as T;
  } catch (err) {
    clearTimeout(timeoutId);

    if (err instanceof ApiClientError) {
      throw err;
    }

    if (err instanceof DOMException && err.name === 'AbortError') {
      throw new ApiClientError('TIMEOUT', 'Request timed out after waiting for the server.');
    }

    if (err instanceof TypeError) {
      // Network-level failure (CORS, offline, DNS, etc.)
      throw new ApiClientError(
        'NETWORK_ERROR',
        'Cannot reach the backend. Check that the server is running.',
      );
    }

    throw new ApiClientError('INTERNAL', 'An unexpected error occurred.');
  }
}

// ─── API functions ─────────────────────────────────────────────────────────────

/**
 * GET /api/health
 * Check backend feed health and LLM availability.
 */
export async function getHealth(): Promise<HealthResponse> {
  return apiFetch<HealthResponse>('/api/health', {}, 5_000);
}

/**
 * GET /api/clusters?hours=24
 * Retrieve available active-fire clusters from NASA FIRMS.
 * Backend returns a bare array of ClusterItem.
 */
export async function getClusters(hours = 48): Promise<ClusterItem[]> {
  return apiFetch<ClusterItem[]>(`/api/clusters?hours=${hours}`);
}

/**
 * POST /api/plan
 * Submit an asynchronous wildfire spread simulation and evacuation planning job.
 * Returns 202 with job_id.
 */
export async function postPlan(request: PlanRequest): Promise<PlanJobResponse> {
  return apiFetch<PlanJobResponse>('/api/plan', {
    method: 'POST',
    body: JSON.stringify(request),
  });
}

/**
 * GET /api/jobs/{job_id}
 * Poll job status, progress, trace and final simulation results.
 */
export async function getJob(jobId: string): Promise<JobStatusResponse> {
  return apiFetch<JobStatusResponse>(`/api/jobs/${encodeURIComponent(jobId)}`, {}, 10_000);
}

/**
 * POST /api/monitor
 * Enable or disable autonomous background polling and evaluation.
 */
export async function postMonitor(request: MonitorRequest): Promise<MonitorStatusResponse> {
  return apiFetch<MonitorStatusResponse>('/api/monitor', {
    method: 'POST',
    body: JSON.stringify(request),
  });
}

/**
 * GET /api/monitor
 * Inspect current autonomous background monitor state.
 */
export async function getMonitor(): Promise<MonitorStatusResponse> {
  return apiFetch<MonitorStatusResponse>('/api/monitor');
}

/**
 * GET /api/assumptions
 * Retrieve full engineering and physical assumptions documentation.
 */
export async function getAssumptions(): Promise<AssumptionsResponse> {
  return apiFetch<AssumptionsResponse>('/api/assumptions');
}

/**
 * GET /api/validation
 * Retrieve empirical wildfire spread validation table.
 */
export async function getValidation(): Promise<ValidationResponse> {
  return apiFetch<ValidationResponse>('/api/validation');
}

// ─── Re-exports ────────────────────────────────────────────────────────────────

export { ApiClientError };
export type { ErrorResponse, ErrorResponse as ApiErrorResponse };
