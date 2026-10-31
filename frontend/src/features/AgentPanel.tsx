/**
 * AgentPanel — autonomous monitoring agent status and briefing.
 * Full implementation in F5 and F6.
 */

import { Panel } from '@/components/Panel';
import { EmptyState } from '@/components/EmptyState';
import type { TraceStepModel } from '@/types';

interface AgentPanelProps {
  isMonitoring: boolean;
  onToggleMonitoring: () => void;
  lastCheck?: string;
  currentStage?: string;
  trace?: TraceStepModel[];
  briefing?: string;
}

export function AgentPanel({
  isMonitoring,
  onToggleMonitoring,
  lastCheck,
  currentStage,
  trace,
  briefing,
}: AgentPanelProps) {
  const recentTrace = trace?.slice(-5).reverse();

  return (
    <Panel
      title="Agent"
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
        {/* Status row */}
        <div className="flex items-center justify-between text-[11px]">
          <span className="text-[#8b98a9]">Status</span>
          <span className={isMonitoring ? 'text-[#2ecc71]' : 'text-[#657787]'}>
            {isMonitoring ? 'Monitoring' : 'Idle'}
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
            <span className="text-[#8b98a9]">Stage</span>
            <span className="text-[#e6edf3]">{currentStage}</span>
          </div>
        )}

        {/* Briefing */}
        {briefing ? (
          <div className="border border-[#162733] rounded p-2">
            <p className="text-[10px] text-[#657787] uppercase tracking-widest mb-1.5">
              Latest Briefing
            </p>
            <p className="text-[11px] text-[#8b98a9] leading-relaxed">{briefing}</p>
          </div>
        ) : (
          <EmptyState
            icon="◈"
            title="No briefing available"
            description="Enable monitoring or run a simulation."
          />
        )}

        {/* Trace */}
        {recentTrace && recentTrace.length > 0 && (
          <div>
            <p className="text-[10px] text-[#657787] uppercase tracking-widest mb-1.5">
              Recent Activity
            </p>
            <ul className="flex flex-col gap-1.5" aria-label="Agent trace">
              {recentTrace.map((entry, i) => {
                const isErr = entry.status === 'error';
                const isDone = entry.status === 'ok' || entry.status === 'done';
                return (
                  <li key={i} className="flex items-start gap-1.5 text-[11px]">
                    <span
                      className={`mt-0.5 flex-shrink-0 ${
                        isErr
                          ? 'text-[#ff3b30]'
                          : isDone
                          ? 'text-[#2ecc71]'
                          : 'text-[#f5a524]'
                      }`}
                      aria-hidden="true"
                    >
                      ▸
                    </span>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center justify-between gap-1">
                        <span className="text-[#e6edf3] font-medium truncate">
                          {entry.step}
                        </span>
                        {entry.duration_ms !== undefined && (
                          <span className="text-[10px] text-[#657787] font-mono flex-shrink-0">
                            {Math.round(entry.duration_ms)}ms
                          </span>
                        )}
                      </div>
                      {entry.note && (
                        <p className="text-[10px] text-[#8b98a9] truncate mt-0.5">
                          {entry.note}
                        </p>
                      )}
                    </div>
                  </li>
                );
              })}
            </ul>
          </div>
        )}
      </div>
    </Panel>
  );
}
