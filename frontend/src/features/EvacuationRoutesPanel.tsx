/**
 * EvacuationRoutesPanel — summarises fire-aware evacuation routes and cut
 * naive baseline segments from the backend PlanResult.
 *
 * IMPORTANT label distinction:
 *   result.routes             → fire-aware safe routes (LIVE re-planned)
 *   result.naive_cut_segments → cut segments of naive baseline routes only
 *                               (NOT all naive routes)
 */

import { Panel } from '@/components/Panel';
import { formatArrivalMinutes } from '@/utils/format';
import type {
  CutSegmentsFeatureCollection,
  JobStatus,
  RoutesFeatureCollection,
  SettlementsFeatureCollection,
} from '@/types';

interface EvacuationRoutesPanelProps {
  settlements: SettlementsFeatureCollection | null;
  routes: RoutesFeatureCollection | null;
  naiveCutSegments: CutSegmentsFeatureCollection | null;
  selectedSettlementId: string | null;
  onSelectSettlement?: (id: string | null) => void;
  jobStatus: JobStatus | null;
}

export function EvacuationRoutesPanel({
  settlements,
  routes,
  naiveCutSegments,
  selectedSettlementId,
  jobStatus,
}: EvacuationRoutesPanelProps) {
  const isLoading = jobStatus === 'queued' || jobStatus === 'running';
  const isDone = jobStatus === 'done';

  const safeRouteCount = routes?.features?.length ?? 0;
  const cutSegmentCount = naiveCutSegments?.features?.length ?? 0;

  // Matching settlement metadata (holds real route_travel_min from backend)
  const selectedSettlement =
    selectedSettlementId && settlements?.features
      ? settlements.features.find(
          (s) => s.properties?.id === selectedSettlementId,
        )
      : null;

  // Routes and cut segments for the currently selected settlement
  const selectedRoutes =
    selectedSettlementId && routes?.features
      ? routes.features.filter(
          (f) => f.properties?.settlement_id === selectedSettlementId,
        )
      : [];

  const selectedCutSegments =
    selectedSettlementId && naiveCutSegments?.features
      ? naiveCutSegments.features.filter(
          (f) => f.properties?.settlement_id === selectedSettlementId,
        )
      : [];

  return (
    <Panel title="Evacuation Routes" icon="→" collapsible defaultCollapsed={false}>
      {isLoading && (
        <div className="p-3 flex items-center gap-2 text-xs text-[#8b98a9]">
          <span
            className="w-1.5 h-1.5 rounded-full bg-[#ff6a2b] animate-pulse inline-block"
            aria-hidden="true"
          />
          Computing evacuation routes…
        </div>
      )}

      {jobStatus === 'error' && (
        <div className="p-3 flex items-center gap-2 text-xs text-[#ff3b30]">
          <span aria-hidden="true">✕</span>
          Simulation failed. No route data available.
        </div>
      )}

      {!isLoading && !isDone && jobStatus !== 'error' && (
        <div className="p-3">
          <p className="text-xs text-[#8b98a9] leading-relaxed">
            Fire-aware and baseline route recommendations will appear here after simulation.
          </p>
        </div>
      )}

      {isDone && (
        <div className="flex flex-col gap-0">
          {/* Summary counts */}
          <div className="divide-y divide-[#162733]">
            <div className="flex items-center justify-between px-3 py-2">
              <span className="text-[11px] text-[#8b98a9]">Fire-aware recommended routes</span>
              <span className="text-[11px] font-mono font-semibold text-[#2ecc71]">
                {safeRouteCount}
              </span>
            </div>
            <div className="flex items-center justify-between px-3 py-2">
              <span className="text-[11px] text-[#8b98a9]">Baseline segments cut by fire</span>
              <span
                className={`text-[11px] font-mono font-semibold ${
                  cutSegmentCount > 0 ? 'text-[#f5a524]' : 'text-[#657787]'
                }`}
              >
                {cutSegmentCount}
              </span>
            </div>
          </div>

          {/* Selected settlement detail */}
          {selectedSettlementId && (
            <div className="mt-1 border-t border-[#162733] px-3 py-2">
              <div className="text-[10px] uppercase tracking-wider text-[#657787] mb-1.5">
                Selected Settlement Routes
              </div>

              {selectedRoutes.length > 0 ? (
                <div className="flex flex-col gap-1">
                  {selectedRoutes.map((_f, idx) => {
                    const travelMin = selectedSettlement?.properties?.route_travel_min;
                    return (
                      <div
                        key={idx}
                        className="flex items-center justify-between text-[11px]"
                      >
                        <span className="text-[#2ecc71] flex items-center gap-1">
                          <span aria-hidden="true">▲</span>
                          Recommended route {idx + 1}
                        </span>
                        <span className="font-mono text-[#e6edf3]">
                          {formatArrivalMinutes(travelMin)}
                        </span>
                      </div>
                    );
                  })}
                </div>
              ) : (
                <p className="text-[11px] text-[#657787]">
                  No fire-aware route found for this settlement.
                </p>
              )}

              {selectedCutSegments.length > 0 && (
                <div className="mt-1.5 flex items-center gap-1 text-[10px] text-[#f5a524]">
                  <span aria-hidden="true">⚠</span>
                  <span>
                    {selectedCutSegments.length} baseline segment
                    {selectedCutSegments.length !== 1 ? 's' : ''} cut by fire
                  </span>
                </div>
              )}
            </div>
          )}

          {isDone && safeRouteCount === 0 && cutSegmentCount === 0 && (
            <div className="px-3 py-2">
              <p className="text-xs text-[#8b98a9] leading-relaxed">
                No route data available for this simulation.
              </p>
            </div>
          )}
        </div>
      )}
    </Panel>
  );
}

