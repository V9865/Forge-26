/**
 * useJobPoller — polls /api/jobs/{job_id} with adaptive backoff.
 *
 * Polling rules:
 * - Every 1s for the first 20s.
 * - Every 2s thereafter.
 * - Stops on 'done' or 'error' status.
 * - Cleans up on unmount or job change.
 * - Network failures set status to 'error' and clear isPolling.
 */

import { useEffect, useRef, useState } from 'react';
import { getJob, ApiClientError } from '@/api/client';
import type { JobStatus, JobStatusResponse } from '@/types';

interface UseJobPollerResult {
  data: JobStatusResponse | null;
  status: JobStatus | null;
  isPolling: boolean;
  error: string | null;
}

export function useJobPoller(jobId: string | null): UseJobPollerResult {
  const [data, setData] = useState<JobStatusResponse | null>(null);
  const [status, setStatus] = useState<JobStatus | null>(null);
  const [isPolling, setIsPolling] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    let isCancelled = false;

    if (timeoutRef.current) {
      clearTimeout(timeoutRef.current);
      timeoutRef.current = null;
    }

    const initTimer = setTimeout(() => {
      if (isCancelled) return;

      if (!jobId) {
        setData(null);
        setStatus(null);
        setIsPolling(false);
        setError(null);
        return;
      }

      const startTime = Date.now();
      setData(null);
      setStatus('queued');
      setIsPolling(true);
      setError(null);

      const scheduleNextPoll = (id: string, delay: number) => {
        timeoutRef.current = setTimeout(() => {
          void executePoll(id);
        }, delay);
      };

      const executePoll = async (id: string) => {
        if (isCancelled) return;

        try {
          const result = await getJob(id);
          if (isCancelled) return;

          setData(result);
          setStatus(result.status);

          if (result.status === 'done' || result.status === 'error') {
            setIsPolling(false);
            return;
          }

          const elapsed = Date.now() - startTime;
          const delay = elapsed < 20_000 ? 1_000 : 2_000;
          scheduleNextPoll(id, delay);
        } catch (err) {
          if (isCancelled) return;

          const message =
            err instanceof ApiClientError
              ? err.message
              : 'Failed to poll job status.';

          setError(message);
          setStatus('error');
          setIsPolling(false);
        }
      };

      void executePoll(jobId);
    }, 0);

    return () => {
      isCancelled = true;
      clearTimeout(initTimer);
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
        timeoutRef.current = null;
      }
    };
  }, [jobId]);

  return { data, status, isPolling, error };
}
