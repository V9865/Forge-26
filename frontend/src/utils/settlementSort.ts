/**
 * Settlement sorting utilities.
 *
 * Implements a deterministic, antisymmetric comparator:
 * 1. Status priority: ALREADY_BURNING → TRAPPED → EVACUATE → NOT_THREATENED.
 * 2. Non-null departure deadlines sorted ascending (earliest departure first).
 * 3. Null/undefined deadlines sorted after non-null deadlines.
 * 4. When deadlines are both null or equal, deterministic tie-breakers:
 *    settlement name (localeCompare), then settlement id (localeCompare).
 * 5. Pure function: never mutates input collections.
 */

import type { Feature, Point } from 'geojson';
import type { SettlementProperties, SettlementStatus } from '@/types';

export const STATUS_SORT_ORDER: Record<SettlementStatus, number> = {
  ALREADY_BURNING: 0,
  TRAPPED: 1,
  EVACUATE: 2,
  NOT_THREATENED: 3,
};

/**
 * Deterministic comparison function for two settlement GeoJSON features.
 * Adheres strictly to mathematical weak ordering rules (reflexivity, antisymmetry, transitivity).
 */
export function compareSettlements(
  a: Feature<Point, SettlementProperties>,
  b: Feature<Point, SettlementProperties>,
): number {
  // 1. Status priority
  const sa = STATUS_SORT_ORDER[a.properties.status] ?? 4;
  const sb = STATUS_SORT_ORDER[b.properties.status] ?? 4;
  if (sa !== sb) {
    return sa - sb;
  }

  // 2. Departure deadline: non-null ascending, nulls/undefined last
  const da = a.properties.depart_by_min;
  const db = b.properties.depart_by_min;
  const hasA = da !== null && da !== undefined;
  const hasB = db !== null && db !== undefined;

  if (hasA && !hasB) return -1;
  if (!hasA && hasB) return 1;
  if (hasA && hasB && da !== db) {
    return (da as number) - (db as number);
  }

  // 3. Deterministic tie-breaker: settlement name
  const nameA = a.properties.name ?? '';
  const nameB = b.properties.name ?? '';
  const nameCmp = nameA.localeCompare(nameB);
  if (nameCmp !== 0) {
    return nameCmp;
  }

  // 4. Final tie-breaker: settlement id
  const idA = a.properties.id ?? '';
  const idB = b.properties.id ?? '';
  return idA.localeCompare(idB);
}

/**
 * Sorts settlement features immutably.
 */
export function sortSettlements(
  features: readonly Feature<Point, SettlementProperties>[],
): Feature<Point, SettlementProperties>[] {
  return [...features].sort(compareSettlements);
}

