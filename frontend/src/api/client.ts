/**
 * EmberRoute — Centralized API client
 *
 * All backend communication is routed through this module.
 * Do not scatter fetch() calls across UI components.
 */

import type {
  ApiErrorResponse,
  AssumptionsResponse,
  ClustersResponse,
  HealthResponse,
  JobPollResponse,
  MonitorRequest,
  MonitorStatus,
  PlanRequest,
  PlanResponse,
  ValidationResponse,
} from '@/types';

// ─── Configuration ─────────────────────────────────────────────────────────────

const BASE_URL = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? '';
const DEFAULT_TIMEOUT_MS = 15_000;

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
      let errorBody: ApiErrorResponse | null = null;
      try {
        errorBody = (await response.json()) as ApiErrorResponse;
      } catch {
        // Ignore parse failure
      }

      const code = errorBody?.error?.code ?? 'HTTP_ERROR';
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
 * Check backend availability.
 */
export async function getHealth(): Promise<HealthResponse> {
  return apiFetch<HealthResponse>('/api/health', {}, 5_000);
}

/**
 * GET /api/clusters?hours=24
 * Retrieve available active-fire clusters.
 */
export async function getClusters(hours = 24): Promise<ClustersResponse> {
  return apiFetch<ClustersResponse>(`/api/clusters?hours=${hours}`);
}

/**
 * POST /api/plan
 * Start a fire-spread and evacuation planning job.
 * Returns 202 with a job_id.
 */
export async function postPlan(request: PlanRequest): Promise<PlanResponse> {
  return apiFetch<PlanResponse>('/api/plan', {
    method: 'POST',
    body: JSON.stringify(request),
  });
}

/**
 * GET /api/jobs/{job_id}
 * Poll job status and results.
 */
export async function getJob(jobId: string): Promise<JobPollResponse> {
  return apiFetch<JobPollResponse>(`/api/jobs/${encodeURIComponent(jobId)}`, {}, 10_000);
}

/**
 * POST /api/monitor
 * Enable or disable the autonomous monitoring agent.
 */
export async function postMonitor(request: MonitorRequest): Promise<void> {
  await apiFetch<unknown>('/api/monitor', {
    method: 'POST',
    body: JSON.stringify(request),
  });
}

/**
 * GET /api/monitor
 * Get current monitoring status.
 */
export async function getMonitor(): Promise<MonitorStatus> {
  return apiFetch<MonitorStatus>('/api/monitor');
}

/**
 * GET /api/assumptions
 * Get model assumptions and data source metadata.
 */
export async function getAssumptions(): Promise<AssumptionsResponse> {
  return apiFetch<AssumptionsResponse>('/api/assumptions');
}

/**
 * GET /api/validation
 * Get validation metrics.
 */
export async function getValidation(): Promise<ValidationResponse> {
  return apiFetch<ValidationResponse>('/api/validation');
}

// ─── Re-exports ────────────────────────────────────────────────────────────────

export { ApiClientError };
export type { ApiErrorResponse };
