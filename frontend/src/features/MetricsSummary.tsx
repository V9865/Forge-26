/**
 * MetricsSummary — displays aggregate evacuation metrics from the backend
 * PlanResult. Only renders metrics that are present and non-null.
 * Never converts missing values to zero.
 */

import { Panel } from '@/components/Panel';
import { formatArrivalMinutes } from '@/utils/format';

interface MetricsSummaryProps {
  metrics: Record<string, unknown> | null | undefined;
}

interface MetricRow {
  key: string;
  label: string;
  format?: 'minutes' | 'number';
  /** Optional accent colour class for the value */
  accentClass?: string;
}

/**
 * Ordered display map. Only rows whose key is non-null in metrics are shown.
 * Sensitive counts (trapped, burning) receive a red accent.
 */
const METRIC_ROWS: MetricRow[] = [
  { key: 'n_settlements_total', label: 'Settlements in AOI', format: 'number' },
  { key: 'n_shelters_total', label: 'Shelter Sites', format: 'number' },
  { key: 'n_threatened', label: 'Threatened', format: 'number', accentClass: 'text-[#f5a524]' },
  { key: 'n_evacuate', label: 'Can Evacuate', format: 'number', accentClass: 'text-[#2ecc71]' },
  { key: 'n_trapped', label: 'Trapped', format: 'number', accentClass: 'text-[#ff3b30]' },
  { key: 'n_already_burning', label: 'Already Burning', format: 'number', accentClass: 'text-[#ff3b30]' },
  { key: 'n_naive_cut', label: 'Baseline Routes Cut', format: 'number', accentClass: 'text-[#f5a524]' },
  { key: 'n_rescued_by_replan', label: 'Rescued by Replanning', format: 'number', accentClass: 'text-[#2ecc71]' },
  { key: 'min_depart_by_min', label: 'Earliest Depart By', format: 'minutes', accentClass: 'text-[#ff3b30]' },
  { key: 'median_depart_by_min', label: 'Median Depart By', format: 'minutes' },
];

/**
 * Format a raw metric value for display.
 * Returns null if the value is null, undefined, or not a number.
 */
function formatMetricValue(value: unknown, format: MetricRow['format']): string | null {
  if (value === null || value === undefined) return null;
  if (typeof value !== 'number') return null;

  if (format === 'minutes') {
    return formatArrivalMinutes(value);
  }
  return String(value);
}

export function MetricsSummary({ metrics }: MetricsSummaryProps) {
  if (!metrics) return null;

  const visibleRows = METRIC_ROWS.filter((row) => {
    const raw = metrics[row.key];
    return raw !== null && raw !== undefined;
  });

  if (visibleRows.length === 0) return null;

  return (
    <Panel title="Evacuation Summary" icon="◈" collapsible defaultCollapsed={false}>
      <dl className="divide-y divide-[#162733]">
        {visibleRows.map((row) => {
          const raw = metrics[row.key];
          const formatted = formatMetricValue(raw, row.format ?? 'number');

          return (
            <div
              key={row.key}
              className="flex items-center justify-between px-3 py-1.5"
            >
              <dt className="text-[11px] text-[#8b98a9] pr-2 truncate">{row.label}</dt>
              <dd
                className={`text-[11px] font-mono font-semibold tabular-nums shrink-0 ${
                  row.accentClass ?? 'text-[#e6edf3]'
                }`}
              >
                {formatted ?? '—'}
              </dd>
            </div>
          );
        })}
      </dl>
    </Panel>
  );
}

