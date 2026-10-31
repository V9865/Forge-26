/**
 * SimulationPanel — mode selection, controls, and job status.
 * Full controls implemented in F3.
 */

import { Panel } from '@/components/Panel';
import type { JobPollResponse, OperatingMode, SimulationResolution } from '@/types';

interface SimulationPanelProps {
  mode: OperatingMode;
  onModeChange: (mode: OperatingMode) => void;
  resolution: SimulationResolution;
  onResolutionChange: (res: SimulationResolution) => void;
  canSubmit: boolean;
  onSubmit: () => void;
  isSubmitting: boolean;
  jobData: JobPollResponse | null;
}

const RESOLUTIONS: SimulationResolution[] = [60, 90, 120];

export function SimulationPanel({
  mode,
  onModeChange,
  resolution,
  onResolutionChange,
  canSubmit,
  onSubmit,
  isSubmitting,
  jobData,
}: SimulationPanelProps) {
  const isRunning =
    jobData?.status === 'PENDING' || jobData?.status === 'RUNNING';

  return (
    <Panel title="Simulation" icon="▶" collapsible>
      <div className="p-3 flex flex-col gap-3">
        {/* Mode selection */}
        <div>
          <p className="text-[10px] text-[#657787] uppercase tracking-widest mb-1.5">
            Operating Mode
          </p>
          <div className="flex gap-1" role="group" aria-label="Operating mode">
            {(['LIVE', 'SCENARIO'] as OperatingMode[]).map((m) => (
              <button
                key={m}
                onClick={() => onModeChange(m)}
                aria-pressed={mode === m}
                className={`flex-1 py-1.5 text-[11px] font-semibold tracking-widest uppercase rounded border transition-colors ${
                  mode === m
                    ? m === 'LIVE'
                      ? 'border-[#2ecc71]/50 text-[#2ecc71] bg-[#2ecc71]/10'
                      : 'border-[#f5a524]/50 text-[#f5a524] bg-[#f5a524]/10'
                    : 'border-[#162733] text-[#8b98a9] hover:border-[#1e3448] hover:text-[#e6edf3]'
                }`}
              >
                {m}
              </button>
            ))}
          </div>
        </div>

        {/* Resolution selection */}
        <div>
          <p className="text-[10px] text-[#657787] uppercase tracking-widest mb-1.5">
            Resolution
          </p>
          <div className="flex gap-1" role="group" aria-label="Simulation resolution">
            {RESOLUTIONS.map((r) => (
              <button
                key={r}
                onClick={() => onResolutionChange(r)}
                aria-pressed={resolution === r}
                className={`flex-1 py-1.5 text-[11px] font-semibold rounded border transition-colors tabular-nums ${
                  resolution === r
                    ? 'border-[#ff6a2b]/50 text-[#ff6a2b] bg-[#ff6a2b]/10'
                    : 'border-[#162733] text-[#8b98a9] hover:border-[#1e3448] hover:text-[#e6edf3]'
                }`}
              >
                {r}m
              </button>
            ))}
          </div>
        </div>

        {/* Scenario note */}
        {mode === 'SCENARIO' && (
          <p className="text-[11px] text-[#f5a524] bg-[#f5a524]/10 border border-[#f5a524]/20 rounded px-2 py-1.5 leading-relaxed">
            ◆ Scenario mode — click the map to place an ignition point.
          </p>
        )}

        {/* Job progress */}
        {isRunning && (
          <div>
            <div className="flex justify-between text-[11px] mb-1">
              <span className="text-[#8b98a9]">{jobData?.stage ?? 'Initialising…'}</span>
              <span className="tabular-nums text-[#f5a524]">
                {jobData?.progress !== undefined ? `${Math.round(jobData.progress)}%` : '…'}
              </span>
            </div>
            <div className="w-full h-1 bg-[#162733] rounded-full overflow-hidden">
              <div
                className="h-full bg-[#ff6a2b] rounded-full transition-all duration-300"
                style={{ width: `${jobData?.progress ?? 0}%` }}
                role="progressbar"
                aria-valuenow={jobData?.progress ?? 0}
                aria-valuemin={0}
                aria-valuemax={100}
              />
            </div>
          </div>
        )}

        {/* Submit button */}
        <button
          onClick={onSubmit}
          disabled={!canSubmit || isSubmitting || isRunning}
          className={`w-full py-2 rounded text-sm font-semibold tracking-wide transition-all ${
            canSubmit && !isSubmitting && !isRunning
              ? 'bg-[#ff6a2b] hover:bg-[#ff8a4a] text-white'
              : 'bg-[#162733] text-[#657787] cursor-not-allowed'
          }`}
          aria-busy={isSubmitting || isRunning}
        >
          {isRunning
            ? 'Running…'
            : isSubmitting
            ? 'Submitting…'
            : 'Run Simulation'}
        </button>

        {/* Cluster selection note */}
        {!canSubmit && mode === 'LIVE' && (
          <p className="text-[11px] text-[#657787] text-center">
            Select a fire cluster first
          </p>
        )}
      </div>
    </Panel>
  );
}

