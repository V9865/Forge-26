/**
 * useBackendHealth — polls /api/health to determine connection status.
 * Polls every 30s on mount and whenever the tab regains focus.
 */

import { useCallback, useEffect, useState } from 'react';
import { getHealth } from '@/api/client';
import type { ConnectionStatus } from '@/types';

interface UseBackendHealthResult {
  status: ConnectionStatus;
  lastChecked: Date | null;
  check: () => void;
}

export function useBackendHealth(pollIntervalMs = 30_000): UseBackendHealthResult {
  const [status, setStatus] = useState<ConnectionStatus>('CONNECTING');
  const [lastChecked, setLastChecked] = useState<Date | null>(null);

  const check = useCallback(async () => {
    try {
      await getHealth();
      setStatus('CONNECTED');
    } catch {
      setStatus('DISCONNECTED');
    } finally {
      setLastChecked(new Date());
    }
  }, []);

  useEffect(() => {
    let isSubscribed = true;

    const performHealthCheck = async () => {
      try {
        await getHealth();
        if (isSubscribed) {
          setStatus('CONNECTED');
        }
      } catch {
        if (isSubscribed) {
          setStatus('DISCONNECTED');
        }
      } finally {
        if (isSubscribed) {
          setLastChecked(new Date());
        }
      }
    };

    // Schedule initial check asynchronously to avoid synchronous setState in effect
    const initialTimer = setTimeout(() => {
      void performHealthCheck();
    }, 0);

    const interval = setInterval(() => {
      void performHealthCheck();
    }, pollIntervalMs);

    const onFocus = () => {
      void performHealthCheck();
    };
    window.addEventListener('focus', onFocus);

    return () => {
      isSubscribed = false;
      clearTimeout(initialTimer);
      clearInterval(interval);
      window.removeEventListener('focus', onFocus);
    };
  }, [pollIntervalMs]);

  return { status, lastChecked, check };
}
