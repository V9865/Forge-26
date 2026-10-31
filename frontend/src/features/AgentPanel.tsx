/**
 * AgentPanel — Autonomous background monitoring status and full pipeline execution trace.
 *
 * Displays:
 * - Autonomous monitoring status & toggle.
 * - Current pipeline execution stage.
 * - Complete collapsible execution trace with stage, timestamp, status, duration,
 *   tool, and diagnostic note.
 */

import { useState } from 'react';
import { Panel } from '@/components/Panel';
import type { TraceStepModel } from '@/types';

interface AgentPanelProps {
  isMonitoring: boolean;
  onToggleMonitoring: () => void;
  lastCheck?: string;
  currentStage?: string;
  trace?: TraceStepModel[];
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

export function AgentPanel({
  isMonitoring,
  onToggleMonitoring,
  lastCheck,
  currentStage,
  trace = [],
}: AgentPanelProps) {
  const [showAllTrace, setShowAllTrace] = useState(false);
  const traceList = trace ?? [];
  const displayTrace = showAllTrace ? traceList : traceList.slice(-8);

  return (
    <Panel
      title="Agent & Telemetry"
      icon="◈"
      collapsible
      defaultCollapsed
      headerSlot={
        <button
          onClick={onToggleMonitoring}
          className={`text-[10px] font-semibold tracking-widest uppercase px-2 py-0.5 rounded border transition-colors ${
            isMonitoring
              ? 'border-[#2ecc71]/40 text-[#2ecc71] bg-[#2ecc71]/10 hover:bg-[#2ecc71]/20'
              : 'border-[#162733] text-[#8b98a9] hover:border-[#1e3448]'
          }`}
          aria-pressed={isMonitoring}
          aria-label={isMonitoring ? 'Disable monitoring' : 'Enable monitoring'}
        >
          {isMonitoring ? 'Active' : 'Enable'}
        </button>
      }
    >
      <div className="p-3 flex flex-col gap-3">
        {/* Monitoring Agent Status */}
        <div className="flex items-center justify-between text-[11px] pb-2 border-b border-[#162733]">
          <span className="text-[#8b98a9]">Autonomous Monitor</span>
          <span
            className={`font-semibold flex items-center gap-1 ${
              isMonitoring ? 'text-[#2ecc71]' : 'text-[#657787]'
            }`}
          >
            <span
              className={`w-1.5 h-1.5 rounded-full ${
                isMonitoring ? 'bg-[#2ecc71] animate-pulse' : 'bg-[#657787]'
              }`}
              aria-hidden="true"
            />
            {isMonitoring ? 'Monitoring AOI' : 'Idle'}
          </span>
        </div>

        {lastCheck && (
          <div className="flex items-center justify-between text-[11px]">
            <span className="text-[#8b98a9]">Last check</span>
            <span className="font-mono text-[#657787]">{lastCheck}</span>
          </div>
        )}

        {currentStage && (
          <div className="flex items-center justify-between text-[11px]">
            <span className="text-[#8b98a9]">Current stage</span>
            <span className="text-[#e6edf3] font-medium">{currentStage}</span>
          </div>
        )}

        {/* Execution Trace Timeline */}
        <div className="flex flex-col gap-1.5 pt-1">
          <div className="flex items-center justify-between">
            <span className="text-[10px] uppercase font-bold tracking-wider text-[#8b98a9]">
              Execution Trace ({traceList.length})
            </span>
            {traceList.length > 8 && (
              <button
                onClick={() => setShowAllTrace((v) => !v)}
                className="text-[10px] text-[#ff6a2b] hover:underline"
              >
                {showAllTrace ? 'Show recent' : `View all (${traceList.length})`}
              </button>
            )}
          </div>

          {traceList.length === 0 ? (
            <p className="text-[11px] text-[#657787] italic py-1">
              No telemetry events recorded yet. Run a simulation to inspect execution trace.
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
