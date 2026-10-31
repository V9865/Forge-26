/**
 * FireIntelligencePanel — NASA FIRMS active fire clusters and intelligence summary.
 *
 * Displays actual backend cluster items from GET /api/clusters:
 * - id, lat, lon, count, total_frp, and suggested_aoi.
 * Handles loading, error, and empty states honestly.
 */

import { Panel } from '@/components/Panel';
import { EmptyState } from '@/components/EmptyState';
import type { ClusterItem } from '@/types';

interface FireIntelligencePanelProps {
  clusters: ClusterItem[];
  selectedClusterId: string | null;
  onSelectCluster: (cluster: ClusterItem | null) => void;
  isLoading: boolean;
  error: string | null;
  onRefresh: () => void;
  feedStatus?: 'OK' | 'STALE' | 'DOWN';
  detectionCount?: number;
}

export function FireIntelligencePanel({
  clusters,
  selectedClusterId,
  onSelectCluster,
  isLoading,
  error,
  onRefresh,
  feedStatus,
  detectionCount,
}: FireIntelligencePanelProps) {
  return (
    <Panel
      title="Fire Intelligence"
      icon="◉"
      collapsible
      headerSlot={
        <button
          onClick={(e) => {
            e.stopPropagation();
            onRefresh();
          }}
          disabled={isLoading}
          className="text-[10px] text-[#8b98a9] hover:text-[#e6edf3] p-1 rounded hover:bg-[#162733] transition-colors disabled:opacity-50"
          title="Refresh active fire clusters from NASA FIRMS"
          aria-label="Refresh fire clusters"
        >
          <span className={`inline-block ${isLoading ? 'animate-spin' : ''}`} aria-hidden="true">
            ↻
          </span>
        </button>
      }
    >
      <div className="flex flex-col">
        {/* Feed status bar */}
        {feedStatus && (
          <div className="flex items-center justify-between px-3 py-1.5 border-b border-[#162733] text-[11px]">
            <span className="text-[#8b98a9]">NASA FIRMS Feed</span>
            <span
              className={`font-semibold tracking-wider ${
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

        {/* Total detections badge if available */}
        {detectionCount !== undefined && detectionCount > 0 && (
          <div className="px-3 py-2 border-b border-[#162733] flex items-baseline justify-between">
            <span className="text-xs text-[#8b98a9]">Detected Hotspots</span>
            <span className="text-sm font-bold font-mono text-[#ff6a2b]">
              {detectionCount.toLocaleString()}
            </span>
          </div>
        )}

        {/* Loading State */}
        {isLoading && (
          <div className="p-4 flex flex-col items-center justify-center gap-2 text-center" role="status">
            <span className="w-5 h-5 border-2 border-[#ff6a2b] border-t-transparent rounded-full animate-spin" />
            <p className="text-xs text-[#8b98a9]">Scanning active fire clusters…</p>
          </div>
        )}

        {/* Error State */}
        {!isLoading && error && (
          <div className="p-3 bg-[#ff3b30]/10 border-b border-[#ff3b30]/20 flex flex-col gap-2">
            <div className="flex items-start gap-1.5 text-[11px] text-[#ff3b30]">
              <span className="font-bold">✕</span>
              <span>{error}</span>
            </div>
            <button
              onClick={onRefresh}
              className="self-start text-[10px] font-semibold uppercase tracking-wider text-[#e6edf3] bg-[#162733] hover:bg-[#1e3448] px-2 py-1 rounded transition-colors"
            >
              Retry
            </button>
          </div>
        )}

        {/* Empty State */}
        {!isLoading && !error && clusters.length === 0 && (
          <div className="p-3">
            <EmptyState
              icon="◉"
              title="No active clusters found"
              description="No high-confidence wildfire clusters found in the last 24h. Use SCENARIO mode to test custom ignitions."
            />
          </div>
        )}

        {/* Clusters List */}
        {!isLoading && !error && clusters.length > 0 && (
          <div className="p-2 flex flex-col gap-2" role="radiogroup" aria-label="Active fire clusters">
            <div className="flex items-center justify-between px-1">
              <span className="text-[10px] uppercase tracking-widest text-[#657787] font-semibold">
                Active Clusters ({clusters.length})
              </span>
              <span className="text-[10px] text-[#8b98a9]">Select to set AOI</span>
            </div>

            {clusters.map((c) => {
              const isSelected = c.id === selectedClusterId;
              const aoi = c.suggested_aoi;
              const widthDeg = (aoi.east - aoi.west).toFixed(2);
              const heightDeg = (aoi.north - aoi.south).toFixed(2);

              return (
                <button
                  key={c.id}
                  onClick={() => onSelectCluster(isSelected ? null : c)}
                  role="radio"
                  aria-checked={isSelected}
                  className={`w-full text-left p-2.5 rounded border transition-all text-xs flex flex-col gap-1.5 ${
                    isSelected
                      ? 'border-[#ff6a2b] bg-[#ff6a2b]/10 shadow-sm'
                      : 'border-[#162733] bg-[#0b0f14]/60 hover:border-[#1e3448] hover:bg-[#121821]'
                  }`}
                >
                  {/* Top line: ID and Detection count */}
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-1.5">
                      <span
                        className={`w-2 h-2 rounded-full ${
                          isSelected ? 'bg-[#ff6a2b]' : 'bg-[#657787]'
                        }`}
                        aria-hidden="true"
                      />
                      <span className="font-bold text-[#e6edf3] uppercase tracking-wide">
                        {c.id}
                      </span>
                    </div>

                    <div className="flex items-center gap-1">
                      <span className="text-[10px] font-mono text-[#ff6a2b] bg-[#ff6a2b]/15 px-1.5 py-0.5 rounded">
                        {c.count} pts
                      </span>
                      {c.total_frp > 0 && (
                        <span className="text-[10px] font-mono text-[#f5a524] bg-[#f5a524]/15 px-1.5 py-0.5 rounded">
                          {Math.round(c.total_frp)} MW
                        </span>
                      )}
                    </div>
                  </div>

                  {/* Centroid Coordinates */}
                  <div className="text-[11px] text-[#8b98a9] flex items-center justify-between">
                    <span>Centroid</span>
                    <span className="font-mono text-[#e6edf3]">
                      {c.lat.toFixed(4)}°N, {c.lon.toFixed(4)}°E
                    </span>
                  </div>

                  {/* Suggested AOI */}
                  <div className="text-[10px] text-[#657787] flex flex-col gap-0.5 pt-1 border-t border-[#162733]/60">
                    <div className="flex justify-between font-mono">
                      <span>Extent ({widthDeg}° × {heightDeg}°)</span>
                      <span className={isSelected ? 'text-[#ff6a2b] font-semibold' : 'text-[#8b98a9]'}>
                        {isSelected ? '✓ AOI Selected' : 'Suggested AOI'}
                      </span>
                    </div>
                    <div className="text-[9px] font-mono text-[#657787] truncate">
                      W:{aoi.west.toFixed(2)} S:{aoi.south.toFixed(2)} E:{aoi.east.toFixed(2)} N:{aoi.north.toFixed(2)}
                    </div>
                  </div>
                </button>
              );
            })}
          </div>
        )}
      </div>
    </Panel>
  );
}
