/**
 * BriefingPanel — Displays the synthesized operational briefing, grounded facts,
 * and pipeline warnings from the backend PlanResult.
 *
 * Distinguishes LLM synthesis from deterministic template fallbacks and lists
 * verified factual citations separately without injecting fake sentence markers.
 */

import { Panel } from '@/components/Panel';
import type { BriefingModel, JobStatus } from '@/types';

interface BriefingPanelProps {
  briefing?: BriefingModel | null;
  warnings?: string[];
  jobStatus: JobStatus | null;
}

export function BriefingPanel({ briefing, warnings = [], jobStatus }: BriefingPanelProps) {
  const isLoading = jobStatus === 'queued' || jobStatus === 'running';
  const isDone = jobStatus === 'done';
  const hasBriefing = Boolean(briefing?.text && briefing.text.trim().length > 0);
  const factEntries = briefing?.facts ? Object.entries(briefing.facts) : [];
  const hasWarnings = warnings && warnings.length > 0;

  return (
    <Panel title="Operational Briefing" icon="📋" collapsible defaultCollapsed={false}>
      {isLoading && (
        <div className="p-3 flex items-center gap-2 text-xs text-[#8b98a9]">
          <span
            className="w-1.5 h-1.5 rounded-full bg-[#ff6a2b] animate-pulse inline-block"
            aria-hidden="true"
          />
          Synthesizing operational briefing…
        </div>
      )}

      {jobStatus === 'error' && (
        <div className="p-3 flex items-center gap-2 text-xs text-[#ff3b30]">
          <span aria-hidden="true">✕</span>
          Simulation failed. No briefing generated.
        </div>
      )}

      {!isLoading && !isDone && jobStatus !== 'error' && (
        <div className="p-3">
          <p className="text-xs text-[#8b98a9] leading-relaxed">
            An operational briefing will be synthesized here after running a simulation.
          </p>
        </div>
      )}

      {isDone && !hasBriefing && (
        <div className="p-3">
          <p className="text-xs text-[#8b98a9] leading-relaxed">
            No briefing text was returned for this simulation run.
          </p>
        </div>
      )}

      {isDone && hasBriefing && briefing && (
        <div className="p-3 flex flex-col gap-3">
          {/* Provenance Header: LLM vs Deterministic Template */}
          <div className="flex flex-wrap items-center justify-between gap-1.5 pb-2 border-b border-[#162733]">
            <div className="flex items-center gap-1.5">
              <span
                className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-semibold uppercase tracking-wider ${
                  briefing.used_llm
                    ? 'bg-[#2ecc71]/15 text-[#2ecc71] border border-[#2ecc71]/30'
                    : 'bg-[#657787]/15 text-[#8b98a9] border border-[#657787]/30'
                }`}
              >
                <span aria-hidden="true">{briefing.used_llm ? '✦' : '⚙'}</span>
                {briefing.used_llm ? 'LLM Synthesized' : 'Deterministic Template'}
              </span>

              {/* Provider and model pill, only when supplied */}
              {(briefing.provider || briefing.model) && (
                <span className="text-[10px] text-[#8b98a9] font-mono">
                  {[briefing.provider, briefing.model].filter(Boolean).join(' · ')}
                </span>
              )}
            </div>

            {/* Dropped sentences badge if fact-checker filtered any */}
            {briefing.dropped_sentences > 0 && (
              <span
                className="text-[10px] text-[#f5a524] flex items-center gap-1"
                title={`${briefing.dropped_sentences} ungrounded sentence(s) removed during fact verification`}
              >
                <span aria-hidden="true">⚠</span>
                <span>{briefing.dropped_sentences} ungrounded filtered</span>
              </span>
            )}
          </div>

          {/* Operational Briefing Prose */}
          <div className="text-xs text-[#e6edf3] leading-relaxed whitespace-pre-line bg-[#0d141d] p-2.5 rounded border border-[#162733]">
            {briefing.text}
          </div>

          {/* Grounded Facts Section */}
          {factEntries.length > 0 && (
            <div className="flex flex-col gap-1.5 pt-1">
              <div className="flex items-center justify-between">
                <span className="text-[10px] uppercase font-bold tracking-wider text-[#8b98a9]">
                  Grounded Facts ({factEntries.length})
                </span>
                <span className="text-[9px] text-[#657787] italic">
                  Extracted from engine facts
                </span>
              </div>

              <div className="flex flex-col gap-1 max-h-48 overflow-y-auto pr-1">
                {factEntries.map(([factId, factText]) => (
                  <div
                    key={factId}
                    className="flex items-start gap-2 p-1.5 bg-[#090d12] rounded border border-[#162733]/60 text-[11px]"
                  >
                    <span className="shrink-0 font-mono font-bold text-[10px] text-[#ff6a2b] bg-[#ff6a2b]/10 px-1 py-0.5 rounded">
                      {factId}
                    </span>
                    <span className="text-[#8b98a9] leading-tight">{factText}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Pipeline Warnings */}
          {hasWarnings && (
            <div className="mt-1 p-2.5 bg-[#f5a524]/10 border border-[#f5a524]/30 rounded">
              <div className="flex items-center gap-1.5 text-[11px] font-semibold text-[#f5a524] mb-1">
                <span aria-hidden="true">⚠</span>
                <span>Pipeline Warnings ({warnings.length})</span>
              </div>
              <ul className="flex flex-col gap-1 text-[11px] text-[#f5a524]/90 list-disc list-inside">
                {warnings.map((warn, i) => (
                  <li key={i} className="leading-snug">
                    {warn}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </Panel>
  );
}

