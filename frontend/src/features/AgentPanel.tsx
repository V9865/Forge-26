/**
 * AgentPanel — Autonomous background monitoring status and full pipeline execution trace.
 *
 * Requirements:
 * - Real integration with FastAPI /api/monitor status and controls.
 * - Displays active/idle state, last evaluation cycle, next scheduled poll, trigger reasons, and current job ID.
 * - Prevents monitor activation with clear explanation when disabled (e.g. SCENARIO mode or missing cluster).
 * - Full execution telemetry trace with duration, timestamp, tool, stage, and note.
 */

import { useState } from 'react';
import { Panel } from '@/components/Panel';
import type { MonitorStatusResponse, TraceStepModel } from '@/types';

interface AgentPanelProps {
  monitorStatus: MonitorStatusResponse | null;
  isMonitorLoading: boolean;
  isMonitorToggling: boolean;
  monitorError: string | null;
  onEnableMonitor: () => void;
  onDisableMonitor: () => void;
  canEnableMonitor: boolean;
  enableDisabledReason?: string;
  currentStage?: string;
  trace?: TraceStepModel[];
  monitoredClusterId?: string | null;
  currentJobId?: string | null;
  jobSource?: 'MANUAL' | 'MONITOR' | null;
}

/** Format UTC timestamp to readable time string */
function formatTraceTime(isoStr?: string | null): string {
  if (!isoStr) return '';
  try {
    const d = new Date(isoStr);
    if (isNaN(d.getTime())) return isoStr;
    return d.toISOString().substring(11, 19) + ' UTC';
  } catch {
    return isoStr;
  }
}

/** Format UTC cycle timestamp */
function formatCycleTime(isoStr?: string | null): string {
  if (!isoStr) return '—';
  try {
    const d = new Date(isoStr);
    if (isNaN(d.getTime())) return isoStr;
    return d.toISOString().substring(11, 19) + ' UTC';
  } catch {
    return isoStr;
  }
}

export function AgentPanel({
  monitorStatus,
  isMonitorLoading,
  isMonitorToggling,
  monitorError,
  onEnableMonitor,
  onDisableMonitor,
  canEnableMonitor,
  enableDisabledReason,
  currentStage,
  trace = [],
  monitoredClusterId,
  currentJobId,
  jobSource,
}: AgentPanelProps) {
  const [showAllTrace, setShowAllTrace] = useState(false);
  const traceList = trace ?? [];
  const displayTrace = showAllTrace ? traceList : traceList.slice(-8);

  const isEnabled = Boolean(monitorStatus?.enabled);

  // Monitor toggle action button
  const headerButton = isMonitorLoading ? (
    <span className="text-[10px] text-[#657787] border border-[#162733] px-2 py-0.5 rounded">
      Checking…
    </span>
  ) : isMonitorToggling ? (
    <span className="text-[10px] text-[#ff6a2b] border border-[#ff6a2b]/30 px-2 py-0.5 rounded flex items-center gap-1">
      <span className="animate-spin text-[9px]" aria-hidden="true">↻</span>
      <span>Updating…</span>
    </span>
  ) : isEnabled ? (
    <button
      onClick={onDisableMonitor}
      className="text-[10px] font-semibold tracking-wider uppercase px-2.5 py-1 min-h-[30px] rounded border border-[#ff3b30]/40 text-[#ff3b30] bg-[#ff3b30]/10 hover:bg-[#ff3b30]/20 transition-colors cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-[#ff3b30]"
      aria-label="Disable autonomous monitoring"
      title="Stop background monitoring"
    >
      Stop Monitor
    </button>
  ) : (
    <button
      onClick={onEnableMonitor}
      disabled={!canEnableMonitor}
      title={!canEnableMonitor ? enableDisabledReason : 'Start autonomous monitoring on selected cluster'}
      className={`text-[10px] font-semibold tracking-wider uppercase px-2.5 py-1 min-h-[30px] rounded border transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-[#2ecc71] ${
        canEnableMonitor
          ? 'border-[#2ecc71]/40 text-[#2ecc71] bg-[#2ecc71]/10 hover:bg-[#2ecc71]/20 cursor-pointer'
          : 'border-[#162733] text-[#657787] opacity-50 cursor-not-allowed'
      }`}
      aria-label="Enable autonomous monitoring"
    >
      Start Monitor
    </button>
  );

  return (
    <Panel
      title="Autonomous Monitor & Trace"
      icon="◈"
      collapsible
      defaultCollapsed={false}
      headerSlot={headerButton}
    >
      <div className="p-3 flex flex-col gap-3">
        {/* ── 1. Autonomous Monitor State ──────────────────────────────── */}
        <div className="flex flex-col gap-2 p-2.5 rounded bg-[#090d12] border border-[#162733]">
          {/* Status Row */}
          <div className="flex items-center justify-between text-[11px] pb-1.5 border-b border-[#162733]">
            <span className="text-[#8b98a9] font-medium">Autonomous Monitor</span>
            <span
              className={`font-semibold flex items-center gap-1.5 ${
                isEnabled ? 'text-[#2ecc71]' : 'text-[#657787]'
              }`}
            >
              <span
                className={`w-2 h-2 rounded-full ${
                  isEnabled ? 'bg-[#2ecc71] animate-pulse' : 'bg-[#657787]'
                }`}
                aria-hidden="true"
              />
              {isEnabled ? 'ACTIVE (LIVE AOI)' : 'IDLE (Stopped)'}
            </span>
          </div>

          {/* Monitored Cluster Target */}
          {isEnabled && (
            <div className="flex items-center justify-between text-[10px]">
              <span className="text-[#8b98a9]">Target Area</span>
              <span className="font-mono text-[#e6edf3] font-semibold">
                {monitoredClusterId
                  ? `Cluster ${monitoredClusterId.toUpperCase()}`
                  : 'Active backend boundary — target identity unavailable'}
              </span>
            </div>
          )}

          {/* Timing Grid: Last Cycle & Next Poll */}
          <div className="grid grid-cols-2 gap-2 text-[10px] pt-0.5">
            <div>
              <span className="text-[9px] uppercase tracking-wider text-[#657787] block">Last Cycle</span>
              <span className="font-mono text-[#e6edf3]">
                {monitorStatus?.last_cycle_utc
                  ? formatCycleTime(monitorStatus.last_cycle_utc)
                  : isEnabled
                  ? 'Awaiting cycle…'
                  : '—'}
              </span>
            </div>
            <div>
              <span className="text-[9px] uppercase tracking-wider text-[#657787] block">Next Evaluation</span>
              <span className="font-mono text-[#e6edf3]">
                {isEnabled && monitorStatus?.next_poll_utc
                  ? formatCycleTime(monitorStatus.next_poll_utc)
                  : '—'}
              </span>
            </div>
          </div>

          {/* Evaluation Trigger Reasons */}
          {isEnabled && monitorStatus?.last_reasons && monitorStatus.last_reasons.length > 0 && (
            <div className="flex flex-col gap-1 pt-1 border-t border-[#162733]">
              <span className="text-[9px] uppercase tracking-wider text-[#8b98a9] font-bold">
                Latest Cycle Triggers ({monitorStatus.last_reasons.length})
              </span>
              <ul className="flex flex-col gap-1 text-[10px]">
                {monitorStatus.last_reasons.map((reason, i) => (
                  <li key={i} className="flex items-start gap-1.5 text-[#e6edf3]">
                    <span className="text-[#ff6a2b] shrink-0">▸</span>
                    <span className="text-[#8b98a9] leading-snug">{reason}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Monitor-Generated Job ID */}
          {monitorStatus?.current_job_id && (
            <div className="flex items-center justify-between text-[10px] pt-1 border-t border-[#162733]">
              <span className="text-[#8b98a9]">Latest Evaluation Job</span>
              <span className="font-mono text-[#ff6a2b] font-semibold flex items-center gap-1">
                <span>{monitorStatus.current_job_id}</span>
                {currentJobId === monitorStatus.current_job_id && jobSource === 'MONITOR' && (
                  <span className="text-[9px] px-1 py-0.2 rounded bg-[#2ecc71]/15 text-[#2ecc71] font-sans">
                    Active
                  </span>
                )}
              </span>
            </div>
          )}

          {/* Error Message */}
          {monitorError && (
            <div className="p-2 text-[10px] text-[#ff3b30] bg-[#ff3b30]/10 border border-[#ff3b30]/20 rounded">
              {monitorError}
            </div>
          )}

          {/* Disabled Reason / Explanation Note */}
          {!isEnabled && enableDisabledReason && (
            <p className="text-[10px] text-[#657787] leading-relaxed pt-1">
              ⓘ {enableDisabledReason}
            </p>
          )}

          {/* Monitored AOI Lock Note */}
          {isEnabled && (
            <p className="text-[10px] text-[#657787] italic leading-relaxed pt-0.5">
              Monitoring is bound to the active cluster selected at start. Stop monitoring to change target area.
            </p>
          )}
        </div>

        {/* ── 2. Pipeline Stage (if active) ────────────────────────────── */}
        {currentStage && (
          <div className="flex items-center justify-between text-[11px] px-1">
            <span className="text-[#8b98a9]">Pipeline Stage</span>
            <span className="text-[#e6edf3] font-medium font-mono">{currentStage}</span>
          </div>
        )}

        {/* ── 3. Execution Telemetry Trace ─────────────────────────────── */}
        <div className="flex flex-col gap-1.5 pt-1">
          <div className="flex items-center justify-between px-1">
            <span className="text-[10px] uppercase font-bold tracking-wider text-[#8b98a9]">
              Telemetry Trace ({traceList.length})
            </span>
            {traceList.length > 8 && (
              <button
                onClick={() => setShowAllTrace((v) => !v)}
                className="text-[10px] text-[#ff6a2b] hover:underline focus:outline-none focus-visible:ring-1 focus-visible:ring-[#ff6a2b] rounded px-1 min-h-[28px] inline-flex items-center"
              >
                {showAllTrace ? 'Show recent' : `View all (${traceList.length})`}
              </button>
            )}
          </div>

          {traceList.length === 0 ? (
            <p className="text-[11px] text-[#657787] italic py-1 px-1">
              No telemetry events recorded yet. Run a simulation or activate monitoring to inspect trace.
            </p>
          ) : (
            <ul className="flex flex-col gap-1.5" aria-label="Execution trace">
              {displayTrace.map((entry, i) => {
                const isErr = entry.status === 'error';
                const isDone = entry.status === 'ok' || entry.status === 'done';
                const timeStr = formatTraceTime(entry.ts_utc);

                return (
                  <li
                    key={i}
                    className="flex items-start gap-2 p-1.5 bg-[#090d12] rounded border border-[#162733]/60 text-[11px]"
                  >
                    <span
                      className={`mt-0.5 shrink-0 ${
                        isErr
                          ? 'text-[#ff3b30]'
                          : isDone
                          ? 'text-[#2ecc71]'
                          : 'text-[#f5a524]'
                      }`}
                      aria-hidden="true"
                    >
                      {isErr ? '✕' : isDone ? '✓' : '▸'}
                    </span>

                    <div className="flex-1 min-w-0">
                      <div className="flex items-center justify-between gap-1">
                        <span className="text-[#e6edf3] font-medium truncate font-mono text-[10px]">
                          {entry.step}
                        </span>

                        <div className="flex items-center gap-1.5 shrink-0">
                          {entry.tool && (
                            <span className="text-[9px] px-1 py-0.2 bg-[#162733] text-[#8b98a9] rounded font-mono">
                              {entry.tool}
                            </span>
                          )}
                          {typeof entry.duration_ms === 'number' && entry.duration_ms > 0 && (
                            <span className="text-[10px] text-[#657787] font-mono">
                              {Math.round(entry.duration_ms)}ms
                            </span>
                          )}
                        </div>
                      </div>

                      <div className="flex items-center justify-between gap-1 mt-0.5">
                        {entry.note ? (
                          <span className="text-[10px] text-[#8b98a9] truncate" title={entry.note}>
                            {entry.note}
                          </span>
                        ) : (
                          <span />
                        )}
                        {timeStr && (
                          <span className="text-[9px] text-[#657787] font-mono shrink-0">
                            {timeStr}
                          </span>
                        )}
                      </div>
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      </div>
    </Panel>
  );
}
