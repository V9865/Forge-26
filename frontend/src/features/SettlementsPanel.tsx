/**
 * SettlementsPanel — displays per-settlement evacuation intelligence from
 * the backend PlanResult. Shows status, arrival/departure times, travel times
 * and naive-cut warnings. Supports selection sync with the map.
 */

import { useEffect, useRef } from 'react';
import { Panel } from '@/components/Panel';
import { formatArrivalMinutes, statusMeta } from '@/utils/format';
import { sortSettlements } from '@/utils/settlementSort';
import type {
  JobStatus,
  RoutesFeatureCollection,
  SettlementsFeatureCollection,
  CutSegmentsFeatureCollection,
} from '@/types';
import type { Feature, Point } from 'geojson';
import type { SettlementProperties } from '@/types';

interface SettlementsPanelProps {
  settlements: SettlementsFeatureCollection | null;
  routes: RoutesFeatureCollection | null;
  naiveCutSegments: CutSegmentsFeatureCollection | null;
  selectedSettlementId: string | null;
  onSelectSettlement: (id: string | null) => void;
  jobStatus: JobStatus | null;
}

export function SettlementsPanel({
  settlements,
  selectedSettlementId,
  onSelectSettlement,
  jobStatus,
}: SettlementsPanelProps) {
  const selectedRowRef = useRef<HTMLDivElement | null>(null);

  // Scroll selected row into view when selection changes
  useEffect(() => {
    if (selectedSettlementId && selectedRowRef.current) {
      selectedRowRef.current.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
  }, [selectedSettlementId]);

  const isLoading = jobStatus === 'queued' || jobStatus === 'running';
  const isDone = jobStatus === 'done';
  const features = settlements?.features ?? [];
  const sorted = sortSettlements(features as Feature<Point, SettlementProperties>[]);

  return (
    <Panel title="Settlements" icon="⬡" collapsible defaultCollapsed={false}>
      {isLoading && (
        <div className="p-3 flex items-center gap-2 text-xs text-[#8b98a9]">
          <span
            className="w-1.5 h-1.5 rounded-full bg-[#ff6a2b] animate-pulse inline-block"
            aria-hidden="true"
          />
          Analysing settlements…
        </div>
      )}

      {jobStatus === 'error' && (
        <div className="p-3 flex items-center gap-2 text-xs text-[#ff3b30]">
          <span aria-hidden="true">✕</span>
          Simulation failed. No settlement data available.
        </div>
      )}

      {!isLoading && !isDone && jobStatus !== 'error' && (
        <div className="p-3">
          <p className="text-xs text-[#8b98a9] leading-relaxed">
            Settlement analysis will appear here after running a simulation.
          </p>
        </div>
      )}

      {isDone && sorted.length === 0 && (
        <div className="p-3">
          <p className="text-xs text-[#8b98a9] leading-relaxed">
            No settlements found within the simulated area.
          </p>
        </div>
      )}

      {isDone && sorted.length > 0 && (
        <div className="flex flex-col divide-y divide-[#162733]" role="list" aria-label="Settlement list">
          {sorted.map((feature) => {
            const p = feature.properties;
            const meta = statusMeta(p.status);
            const isSelected = p.id === selectedSettlementId;

            return (
              <div
                key={p.id}
                ref={isSelected ? selectedRowRef : null}
                role="listitem"
                aria-selected={isSelected}
                tabIndex={0}
                onClick={() => onSelectSettlement(isSelected ? null : p.id)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    onSelectSettlement(isSelected ? null : p.id);
                  }
                }}
                className={`p-2.5 cursor-pointer transition-colors focus:outline-none ${
                  isSelected
                    ? 'bg-[#ff6a2b]/10 border-l-2 border-[#ff6a2b]'
                    : 'hover:bg-[#0d1923] border-l-2 border-transparent'
                }`}
              >
                {/* Header row: name + status badge */}
                <div className="flex items-center justify-between gap-2 mb-1.5">
                  <span
                    className="text-xs font-semibold text-[#e6edf3] truncate"
                    title={p.name}
                  >
                    {p.name}
                  </span>
                  <span
                    className={`shrink-0 inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[10px] font-bold tracking-wide ${meta.bgClass} ${meta.colorClass}`}
                  >
                    <span aria-hidden="true">{meta.icon}</span>
                    {meta.label}
                  </span>
                </div>

                {/* Time metrics grid */}
                <div className="grid grid-cols-3 gap-x-2 text-[10px] text-[#8b98a9]">
                  <div>
                    <div className="text-[9px] uppercase tracking-wider mb-0.5">Arrival</div>
                    <div className="text-[#e6edf3] font-mono">
                      {formatArrivalMinutes(p.fire_arrival_min)}
                    </div>
                  </div>
                  <div>
                    <div className="text-[9px] uppercase tracking-wider mb-0.5">Depart By</div>
                    <div
                      className={`font-mono ${
                        p.depart_by_min !== null && p.depart_by_min !== undefined && p.depart_by_min < 30
                          ? 'text-[#ff3b30] font-bold'
                          : 'text-[#e6edf3]'
                      }`}
                    >
                      {formatArrivalMinutes(p.depart_by_min)}
                    </div>
                  </div>
                  <div>
                    <div className="text-[9px] uppercase tracking-wider mb-0.5">Travel</div>
                    <div className="text-[#e6edf3] font-mono">
                      {formatArrivalMinutes(p.route_travel_min)}
                    </div>
                  </div>
                </div>

                {/* Naive-cut warning */}
                {p.naive_cut && (
                  <div className="mt-1.5 flex items-center gap-1 text-[10px] text-[#f5a524]">
                    <span aria-hidden="true">⚠</span>
                    <span>Baseline route cut by fire</span>
                  </div>
                )}

                {/* Backend note */}
                {p.note && (
                  <div className="mt-1 text-[10px] text-[#657787] italic leading-relaxed">
                    {p.note}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </Panel>
  );
}

