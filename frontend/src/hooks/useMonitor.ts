/**
 * useMonitor — React hook managing FastAPI background autonomous monitor integration.
 *
 * Concurrency & Resilience Guarantees:
 * - Post-precedence race hardening:
 *   Outstanding GET responses are invalidated when a POST begins and when it completes.
 *   GET responses started while a POST is in flight cannot commit before or after POST settles.
 *   Successful POST responses always become the latest confirmed status.
 *   Failed POSTs preserve the last confirmed status and expose the error.
 * - Monotonic GET sequencing (lastCommittedGetSeqRef):
 *   Older concurrent GETs cannot overwrite newer GET responses.
 * - In-flight polling lock (isPollInFlightRef) prevents overlapping poll executions.
 * - Cleanup safe: all timers and async operations guarded on unmount.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { getMonitor, postMonitor, ApiClientError } from '@/api/client';
import type { AOIModel, MonitorRequest, MonitorStatusResponse } from '@/types';

interface UseMonitorResult {
  status: MonitorStatusResponse | null;
  isEnabled: boolean;
  isLoading: boolean;
  isToggling: boolean;
  error: string | null;
  enable: (aoi: AOIModel) => Promise<MonitorStatusResponse | null>;
  disable: () => Promise<MonitorStatusResponse | null>;
  refresh: () => Promise<void>;
  clearError: () => void;
}

const UI_STATUS_POLL_INTERVAL_MS = 6_000;

export function useMonitor(): UseMonitorResult {
  const [status, setStatus] = useState<MonitorStatusResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isToggling, setIsToggling] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Concurrency & lifecycle guards
  const isMountedRef = useRef(true);
  const pollTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const isPollInFlightRef = useRef(false);
  const postInFlightRef = useRef(false);
  const requestSeqRef = useRef(0);
  const minValidGetSeqRef = useRef(0);
  const lastCommittedGetSeqRef = useRef(0);

  // Status fetch with post-precedence and monotonic sequence validation
  const fetchStatus = useCallback(async (silent = false): Promise<MonitorStatusResponse | null> => {
    // Drop silent background poll if one is already in flight
    if (isPollInFlightRef.current && silent) {
      return null;
    }

    // Skip silent background poll if a POST mutation is currently in flight
    if (postInFlightRef.current && silent) {
      return null;
    }

    if (silent) {
      isPollInFlightRef.current = true;
    } else {
      setError(null);
    }

    const seq = ++requestSeqRef.current;

    try {
      const res = await getMonitor();

      // Drop response if:
      // - Component unmounted
      // - A POST is currently in flight (GET would overwrite with pre-mutation data)
      // - Request started before or during a POST (seq < minValidGetSeqRef.current)
      // - A newer GET already committed (seq < lastCommittedGetSeqRef.current)
      const isValid =
        isMountedRef.current &&
        !postInFlightRef.current &&
        seq >= minValidGetSeqRef.current &&
        seq >= lastCommittedGetSeqRef.current;

      if (isValid) {
        lastCommittedGetSeqRef.current = seq;
        setStatus(res);
      }
      return res;
    } catch (err) {
      const isValid =
        isMountedRef.current &&
        !silent &&
        !postInFlightRef.current &&
        seq >= minValidGetSeqRef.current &&
        seq >= lastCommittedGetSeqRef.current;

      if (isValid) {
        const msg =
          err instanceof ApiClientError
            ? err.message
            : 'Could not fetch autonomous monitor status from server.';
        setError(msg);
      }
      return null;
    } finally {
      if (silent) {
        isPollInFlightRef.current = false;
      }
      if (isMountedRef.current && !silent) {
        setIsLoading(false);
      }
    }
  }, []);

  // Initial status hydration on mount
  useEffect(() => {
    isMountedRef.current = true;

    const timer = setTimeout(() => {
      void fetchStatus(false);
    }, 0);

    return () => {
      isMountedRef.current = false;
      clearTimeout(timer);
      if (pollTimerRef.current) {
        clearTimeout(pollTimerRef.current);
        pollTimerRef.current = null;
      }
    };
  }, [fetchStatus]);

  // Periodic status refresh while enabled
  useEffect(() => {
    if (!status?.enabled) {
      if (pollTimerRef.current) {
        clearTimeout(pollTimerRef.current);
        pollTimerRef.current = null;
      }
      return;
    }

    const poll = async () => {
      await fetchStatus(true);
      if (isMountedRef.current && status?.enabled) {
        pollTimerRef.current = setTimeout(() => {
          void poll();
        }, UI_STATUS_POLL_INTERVAL_MS);
      }
    };

    pollTimerRef.current = setTimeout(() => {
      void poll();
    }, UI_STATUS_POLL_INTERVAL_MS);

    return () => {
      if (pollTimerRef.current) {
        clearTimeout(pollTimerRef.current);
        pollTimerRef.current = null;
      }
    };
  }, [status?.enabled, fetchStatus]);

  // Enable action (LIVE mode with explicit AOI)
  const enable = useCallback(
    async (aoi: AOIModel): Promise<MonitorStatusResponse | null> => {
      if (isToggling || postInFlightRef.current) return null;

      setIsToggling(true);
      postInFlightRef.current = true;
      setError(null);

      // Invalidate all outstanding GET requests started before this POST
      minValidGetSeqRef.current = ++requestSeqRef.current;

      const payload: MonitorRequest = {
        enabled: true,
        mode: 'LIVE',
        aoi: {
          west: aoi.west,
          south: aoi.south,
          east: aoi.east,
          north: aoi.north,
        },
        poll_s: 60,
      };

      try {
        const res = await postMonitor(payload);
        if (isMountedRef.current) {
          // A successful POST response always becomes the latest confirmed status
          setStatus(res);
        }
        return res;
      } catch (err) {
        if (isMountedRef.current) {
          // A failed POST must preserve the last confirmed status and expose the error
          const msg =
            err instanceof ApiClientError
              ? err.message
              : 'Failed to enable autonomous monitoring.';
          setError(msg);
        }
        return null;
      } finally {
        // Invalidate all GET responses started while this POST was in flight
        minValidGetSeqRef.current = ++requestSeqRef.current;
        postInFlightRef.current = false;
        if (isMountedRef.current) {
          setIsToggling(false);
        }
      }
    },
    [isToggling],
  );

  // Disable action
  const disable = useCallback(async (): Promise<MonitorStatusResponse | null> => {
    if (isToggling || postInFlightRef.current) return null;

    setIsToggling(true);
    postInFlightRef.current = true;
    setError(null);

    // Invalidate all outstanding GET requests started before this POST
    minValidGetSeqRef.current = ++requestSeqRef.current;

    const payload: MonitorRequest = {
      enabled: false,
    };

    try {
      const res = await postMonitor(payload);
      if (isMountedRef.current) {
        // A successful POST response always becomes the latest confirmed status
        setStatus(res);
      }
      return res;
    } catch (err) {
      if (isMountedRef.current) {
        // A failed POST must preserve the last confirmed status and expose the error
        const msg =
          err instanceof ApiClientError
            ? err.message
            : 'Failed to disable autonomous monitoring.';
        setError(msg);
      }
      return null;
    } finally {
      // Invalidate all GET responses started while this POST was in flight
      minValidGetSeqRef.current = ++requestSeqRef.current;
      postInFlightRef.current = false;
      if (isMountedRef.current) {
        setIsToggling(false);
      }
    }
  }, [isToggling]);

  const clearError = useCallback(() => {
    setError(null);
  }, []);

  const refresh = useCallback(async () => {
    await fetchStatus(false);
  }, [fetchStatus]);

  return {
    status,
    isEnabled: Boolean(status?.enabled),
    isLoading,
    isToggling,
    error,
    enable,
    disable,
    refresh,
    clearError,
  };
}
