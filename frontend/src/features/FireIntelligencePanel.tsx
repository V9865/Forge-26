/**
 * FireIntelligencePanel — fire detection summary and cluster selection.
 * Full implementation in F3 (cluster selection) and F4 (settlement results).
 */

import { Panel } from '@/components/Panel';
import { EmptyState } from '@/components/EmptyState';

interface FireIntelligencePanelProps {
  feedStatus?: 'OK' | 'STALE' | 'DOWN';
  detectionCount?: number;
  feedFreshness?: string;
}

export function FireIntelligencePanel({
  feedStatus,
  detectionCount,
  feedFreshness,
}: FireIntelligencePanelProps) {
  return (
    <Panel title="Fire Intelligence" icon="◉" collapsible>
      {/* Feed status row */}
      {feedStatus && (
        <div className="flex items-center justify-between px-3 py-2 border-b border-[#162733]">
          <span className="text-xs text-[#8b98a9]">NASA FIRMS Feed</span>
          <span
            className={`text-[11px] font-semibold tracking-wider ${
              feedStatus === 'OK'
                ? 'text-[#2ecc71]'
                : feedStatus === 'STALE'
                ? 'text-[#f5a524]'
                : 'text-[#ff3b30]'
            }`}
          >
            {feedStatus}
          </span>
        </div>
      )}

      {detectionCount !== undefined ? (
        <div className="p-3">
          <div className="flex items-baseline gap-2">
            <span className="text-2xl font-bold tabular-nums text-[#e6edf3]">
              {detectionCount.toLocaleString()}
            </span>
            <span className="text-xs text-[#8b98a9]">detections</span>
          </div>
          {feedFreshness && (
            <p className="text-[11px] text-[#657787] font-mono mt-0.5">{feedFreshness}</p>
          )}
        </div>
      ) : (
        <EmptyState
          icon="◉"
          title="No fire data loaded"
          description="Select a cluster or run a simulation to load fire intelligence."
        />
      )}
    </Panel>
  );
}

