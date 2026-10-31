/**
 * ProvenancePanel — Audits data layer provenance for all spatial, meteorological,
 * and infrastructure inputs used in the wildfire simulation.
 *
 * Distinguishes fresh vs stale data strictly using the backend's `is_stale` flag
 * and only makes HTTP/HTTPS URLs clickable.
 */

import { Panel } from '@/components/Panel';
import type { JobStatus, ProvenanceModel } from '@/types';

interface ProvenancePanelProps {
  provenance?: ProvenanceModel[] | null;
  jobStatus: JobStatus | null;
}

/** Check whether a URL is a valid, clickable HTTP or HTTPS link */
function isHttpUrl(url?: string | null): boolean {
  if (!url) return false;
  return /^https?:\/\//i.test(url.trim());
}

/** Format a timestamp string cleanly */
function formatUtcTimestamp(isoStr: string): string {
  if (!isoStr) return '—';
  try {
    const d = new Date(isoStr);
    if (isNaN(d.getTime())) return isoStr;
    return d.toISOString().replace('T', ' ').replace(/\.\d+Z$/, ' UTC');
  } catch {
    return isoStr;
  }
}

export function ProvenancePanel({ provenance, jobStatus }: ProvenancePanelProps) {
  const isLoading = jobStatus === 'queued' || jobStatus === 'running';
  const isDone = jobStatus === 'done';
  const items = provenance ?? [];

  return (
    <Panel title="Data Provenance" icon="🗄" collapsible defaultCollapsed>
      {isLoading && (
        <div className="p-3 flex items-center gap-2 text-xs text-[#8b98a9]">
          <span
            className="w-1.5 h-1.5 rounded-full bg-[#ff6a2b] animate-pulse inline-block"
            aria-hidden="true"
          />
          Recording data layer provenance…
        </div>
      )}

      {jobStatus === 'error' && (
        <div className="p-3 flex items-center gap-2 text-xs text-[#ff3b30]">
          <span aria-hidden="true">✕</span>
          Simulation failed. No provenance audit available.
        </div>
      )}

      {!isLoading && !isDone && jobStatus !== 'error' && (
        <div className="p-3">
          <p className="text-xs text-[#8b98a9] leading-relaxed">
            Data layer provenance and audit records will appear here after simulation.
          </p>
        </div>
      )}

      {isDone && items.length === 0 && (
        <div className="p-3">
          <p className="text-xs text-[#8b98a9] leading-relaxed">
            No provenance records were reported for this run.
          </p>
        </div>
      )}

      {isDone && items.length > 0 && (
        <div className="flex flex-col divide-y divide-[#162733]" role="list" aria-label="Provenance layers">
          {items.map((item, idx) => {
            const hasHttp = isHttpUrl(item.url);

            return (
              <div key={idx} className="p-2.5 flex flex-col gap-1.5" role="listitem">
                {/* Header row: Layer Name + Stale/Fresh Badge */}
                <div className="flex items-start justify-between gap-2">
                  <div className="flex flex-col min-w-0">
                    <span className="text-xs font-semibold text-[#e6edf3] truncate" title={item.name}>
                      {item.name}
                    </span>
                    <span className="text-[10px] text-[#8b98a9] font-medium">
                      Source: <span className="text-[#e6edf3]">{item.source}</span>
                    </span>
                  </div>

                  {/* Freshness Badge based strictly on is_stale */}
                  <span
                    className={`shrink-0 inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-bold tracking-wider ${
                      item.is_stale
                        ? 'bg-[#f5a524]/15 text-[#f5a524] border border-[#f5a524]/30'
                        : 'bg-[#2ecc71]/15 text-[#2ecc71] border border-[#2ecc71]/30'
                    }`}
                  >
                    <span aria-hidden="true">{item.is_stale ? '⚠' : '✓'}</span>
                    {item.is_stale ? 'STALE' : 'FRESH'}
                  </span>
                </div>

                {/* Timing & TTL Metadata */}
                <div className="grid grid-cols-3 gap-1 text-[10px] text-[#8b98a9]">
                  <div>
                    <span className="text-[9px] uppercase tracking-wider block text-[#657787]">Fetched</span>
                    <span className="font-mono text-[#e6edf3] text-[9px]">
                      {formatUtcTimestamp(item.fetched_at_utc)}
                    </span>
                  </div>
                  <div>
                    <span className="text-[9px] uppercase tracking-wider block text-[#657787]">Age</span>
                    <span className="font-mono text-[#e6edf3]">
                      {typeof item.age_s === 'number' ? `${item.age_s}s` : '—'}
                    </span>
                  </div>
                  <div>
                    <span className="text-[9px] uppercase tracking-wider block text-[#657787]">TTL</span>
                    <span className="font-mono text-[#e6edf3]">
                      {typeof item.ttl_s === 'number' ? `${item.ttl_s}s` : '—'}
                    </span>
                  </div>
                </div>

                {/* Source Link / Identifier */}
                {item.url && (
                  <div className="text-[10px] truncate text-[#657787]">
                    <span className="text-[#8b98a9] mr-1">URL:</span>
                    {hasHttp ? (
                      <a
                        href={item.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-[#ff6a2b] hover:underline"
                        title={item.url}
                      >
                        {item.url} ↗
                      </a>
                    ) : (
                      <span className="font-mono text-[#657787]">{item.url}</span>
                    )}
                  </div>
                )}

                {/* Optional Note */}
                {item.note && (
                  <p className="text-[10px] text-[#8b98a9] italic leading-relaxed">
                    {item.note}
                  </p>
                )}
              </div>
            );
          })}
        </div>
      )}
    </Panel>
  );
}

