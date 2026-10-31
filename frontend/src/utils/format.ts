/**
 * EmberRoute — utility helpers
 */

import type { EvacuationStatus } from '@/types';

/**
 * Format a data freshness Date into a human-readable age string.
 */
export function formatAge(date: Date | null): string {
  if (!date) return 'unknown';
  const diffMs = Date.now() - date.getTime();
  const diffSec = Math.floor(diffMs / 1000);
  if (diffSec < 60) return `${diffSec}s ago`;
  const diffMin = Math.floor(diffSec / 60);
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffHr = Math.floor(diffMin / 60);
  return `${diffHr}h ago`;
}

/**
 * Format hours-until-arrival into a human readable string.
 */
export function formatArrivalHours(hours: number | undefined): string {
  if (hours === undefined) return '—';
  if (hours <= 0) return 'Now';
  if (hours < 1) return `${Math.round(hours * 60)} min`;
  if (hours < 2) return `${hours.toFixed(1)} hr`;
  return `${Math.round(hours)} hr`;
}

/**
 * Map EvacuationStatus to its display label and colour class.
 */
export function statusMeta(status: EvacuationStatus): {
  label: string;
  colorClass: string;
  bgClass: string;
  icon: string;
} {
  switch (status) {
    case 'EVACUATE':
      return {
        label: 'EVACUATE',
        colorClass: 'text-[#2ecc71]',
        bgClass: 'bg-[#2ecc71]/15',
        icon: '▲',
      };
    case 'DEPART_SOON':
      return {
        label: 'DEPART SOON',
        colorClass: 'text-[#f5a524]',
        bgClass: 'bg-[#f5a524]/15',
        icon: '◆',
      };
    case 'TRAPPED':
      return {
        label: 'TRAPPED',
        colorClass: 'text-[#ff3b30]',
        bgClass: 'bg-[#ff3b30]/20',
        icon: '✕',
      };
    case 'ALREADY_BURNING':
      return {
        label: 'BURNING',
        colorClass: 'text-white',
        bgClass: 'bg-[#8b1a1a] ring-1 ring-white/80 shadow-sm',
        icon: '◉',
      };
    case 'NOT_THREATENED':
      return {
        label: 'SAFE',
        colorClass: 'text-[#657787]',
        bgClass: 'bg-[#657787]/10',
        icon: '○',
      };
  }
}

/**
 * Format coordinates for display.
 */
export function formatCoords(lon: number, lat: number): string {
  const ns = lat >= 0 ? 'N' : 'S';
  const ew = lon >= 0 ? 'E' : 'W';
  return `${Math.abs(lat).toFixed(4)}°${ns} ${Math.abs(lon).toFixed(4)}°${ew}`;
}

/**
 * Clamp a value between min and max.
 */
export function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}

