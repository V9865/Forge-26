/**
 * SimulationPanel — simulation configuration, scenario controls, wind override, and job progress.
 */

import { Panel } from '@/components/Panel';
import type {
  AOIModel,
  ClusterItem,
  JobStatusResponse,
  OperatingMode,
  SimulationResolution,
} from '@/types';

interface SimulationPanelProps {
  mode: OperatingMode;
  onModeChange: (mode: OperatingMode) => void;
  resolution?: SimulationResolution;
  onResolutionChange?: (res: SimulationResolution) => void;
  // LIVE mode context
  selectedCluster: ClusterItem | null;
  // SCENARIO mode context
  scenarioIgnition: { lat: number; lng: number } | null;
  scenarioAoi: AOIModel | null;
  onClearIgnition: () => void;
  onSelectIgnition?: (pt: { lat: number; lng: number }) => void;
  // Wind override
  isWindOverrideEnabled: boolean;
  onToggleWindOverride: (enabled: boolean) => void;
  windSpeed: number;
  onWindSpeedChange: (speed: number) => void;
  windDirFrom: number;
  onWindDirFromChange: (dir: number) => void;
  // Plan submission
  canSubmit: boolean;
  onSubmit: () => void;
  isSubmitting: boolean;
  submissionError: string | null;
  onDismissError: () => void;
  // Poller status
  jobData: JobStatusResponse | null;
  // Mode lock (e.g. autonomous monitoring active)
  isModeLocked?: boolean;
  modeLockedReason?: string;
}

const PRESET_IGNITIONS = [
  { name: '🏔️ Valais Forest Corridor', lat: 46.275, lng: 7.550, desc: 'Cached OSM network & settlements' },
  { name: '🌲 Montes de Toledo', lat: 39.55, lng: -4.35, desc: 'Pine & shrubland' },
  { name: '🏞️ Sierra Foothills', lat: 37.85, lng: -120.25, desc: 'Chaparral & oaks' },
  { name: '🌿 Algarve Hills', lat: 37.32, lng: -8.55, desc: 'Eucalyptus mountain belt' },
];

function cardinalFromDeg(deg: number): string {
  const directions = ['N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE', 'S', 'SSW', 'SW', 'WSW', 'W', 'WNW', 'NW', 'NNW'];
  const idx = Math.round(((deg % 360) / 22.5)) % 16;
  return directions[idx];
}

export function SimulationPanel({
  mode,
  onModeChange,
  resolution: _resolution,
  onResolutionChange: _onResolutionChange,
  selectedCluster,
  scenarioIgnition,
  scenarioAoi,
  onClearIgnition,
  onSelectIgnition,
  isWindOverrideEnabled,
  onToggleWindOverride,
  windSpeed,
  onWindSpeedChange,
  windDirFrom,
  onWindDirFromChange,
  canSubmit,
  onSubmit,
  isSubmitting,
  submissionError,
  onDismissError,
  jobData,
  isModeLocked = false,
  modeLockedReason,
}: SimulationPanelProps) {
  const isRunning =
    jobData?.status === 'queued' || jobData?.status === 'running';

  const progressPct = Math.min(
    100,
    Math.max(0, Math.round((jobData?.progress ?? 0) * 100)),
  );

  return (
    <Panel title="Simulation" icon="▶" collapsible>
      <div className="p-3 flex flex-col gap-3.5">
        {/* ── 1. Operating Mode ─────────────────────────────────── */}
        <div>
          <div className="flex justify-between items-center mb-1.5">
            <span className="text-[10px] text-[#657787] uppercase tracking-widest font-semibold">
              Operating Mode
            </span>
            <span
              className={`text-[10px] font-mono px-1.5 py-0.5 rounded ${
                mode === 'LIVE'
                  ? 'text-[#2ecc71] bg-[#2ecc71]/10'
                  : 'text-[#f5a524] bg-[#f5a524]/10'
              }`}
            >
              {mode === 'LIVE' ? 'Real NASA FIRMS' : 'Interactive What-If'}
            </span>
          </div>

          <div className="flex gap-1" role="group" aria-label="Operating mode">
            {(['LIVE', 'SCENARIO'] as OperatingMode[]).map((m) => (
              <button
                key={m}
                onClick={() => {
                  if (isModeLocked) return;
                  onModeChange(m);
                }}
                aria-pressed={mode === m}
                disabled={isSubmitting || isRunning || isModeLocked}
                title={isModeLocked ? modeLockedReason : undefined}
                className={`flex-1 py-1.5 min-h-[38px] text-[11px] font-semibold tracking-wider uppercase rounded border transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-[#ff6a2b] ${
                  mode === m
                    ? m === 'LIVE'
                      ? 'border-[#2ecc71]/50 text-[#2ecc71] bg-[#2ecc71]/15 font-bold shadow-xs'
                      : 'border-[#f5a524]/50 text-[#f5a524] bg-[#f5a524]/15 font-bold shadow-xs'
                    : isModeLocked
                    ? 'border-[#162733] text-[#657787] opacity-50 cursor-not-allowed'
                    : 'border-[#162733] text-[#8b98a9] hover:border-[#1e3448] hover:text-[#e6edf3]'
                }`}
              >
                {m}
              </button>
            ))}
          </div>

          {isModeLocked && (
            <div className="mt-1 text-[10px] text-[#f5a524] flex items-center gap-1">
              <span aria-hidden="true">🔒</span>
              <span>{modeLockedReason || 'Operating mode locked while monitoring is active.'}</span>
            </div>
          )}
        </div>

        {/* ── 2. Mode-Specific AOI / Ignition Context ────────────── */}
        {mode === 'LIVE' ? (
          <div className="p-2.5 rounded bg-[#0b0f14]/80 border border-[#162733] text-xs flex flex-col gap-1.5">
            <div className="flex items-center justify-between">
              <span className="text-[10px] uppercase tracking-wider text-[#8b98a9] font-medium">
                Simulation Area (AOI)
              </span>
              {selectedCluster ? (
                <span className="text-[10px] text-[#2ecc71] font-semibold">✓ Cluster Selected</span>
              ) : (
                <span className="text-[10px] text-[#f5a524]">Required</span>
              )}
            </div>

            {selectedCluster ? (
              <div className="flex flex-col gap-1 text-[11px]">
                <div className="flex justify-between font-mono">
                  <span className="text-[#8b98a9]">Cluster ID:</span>
                  <span className="text-[#e6edf3] font-semibold uppercase">{selectedCluster.id}</span>
                </div>
                <div className="flex justify-between font-mono text-[10px]">
                  <span className="text-[#657787]">Suggested AOI:</span>
                  <span className="text-[#8b98a9]">
                    [{selectedCluster.suggested_aoi.west.toFixed(2)}, {selectedCluster.suggested_aoi.south.toFixed(2)},{' '}
                    {selectedCluster.suggested_aoi.east.toFixed(2)}, {selectedCluster.suggested_aoi.north.toFixed(2)}]
                  </span>
                </div>
              </div>
            ) : (
              <p className="text-[11px] text-[#8b98a9] leading-relaxed">
                Select an active fire cluster from the <span className="text-[#ff6a2b]">Fire Intelligence</span> panel
                to define the simulation boundary.
              </p>
            )}
          </div>
        ) : (
          <div className="p-2.5 rounded bg-[#0b0f14]/80 border border-[#f5a524]/30 text-xs flex flex-col gap-2">
            <div className="flex items-center justify-between">
              <span className="text-[10px] uppercase tracking-wider text-[#f5a524] font-semibold flex items-center gap-1">
                <span className="w-1.5 h-1.5 rounded-full bg-[#f5a524] animate-ping" />
                Scenario Ignition
              </span>
              {scenarioIgnition && (
                <button
                  onClick={onClearIgnition}
                  disabled={isSubmitting || isRunning}
                  className="text-[10px] text-[#8b98a9] hover:text-[#ff3b30] underline transition-colors px-1 py-0.5 rounded focus:outline-none focus-visible:ring-1 focus-visible:ring-[#ff6a2b]"
                >
                  Clear
                </button>
              )}
            </div>

            {scenarioIgnition ? (
              <div className="flex flex-col gap-1 text-[11px]">
                <div className="flex justify-between font-mono">
                  <span className="text-[#8b98a9]">Ignition (lat, lon):</span>
                  <span className="text-[#f5a524] font-semibold">
                    {scenarioIgnition.lat.toFixed(4)}°N, {scenarioIgnition.lng.toFixed(4)}°E
                  </span>
                </div>
                {scenarioAoi && (
                  <div className="flex flex-col gap-0.5 pt-1 border-t border-[#162733] font-mono text-[10px]">
                    <div className="flex justify-between text-[#8b98a9]">
                      <span>Scenario AOI:</span>
                      <span>
                        {((scenarioAoi.east - scenarioAoi.west)).toFixed(2)}° ×{' '}
                        {((scenarioAoi.north - scenarioAoi.south)).toFixed(2)}°
                      </span>
                    </div>
                    <div className="text-[9px] text-[#657787] truncate">
                      W:{scenarioAoi.west} S:{scenarioAoi.south} E:{scenarioAoi.east} N:{scenarioAoi.north}
                    </div>
                  </div>
                )}
              </div>
            ) : (
              <p className="text-[11px] text-[#f5a524]/90 leading-relaxed bg-[#f5a524]/10 p-2 rounded border border-[#f5a524]/20">
                Click anywhere on the interactive map to place a scenario ignition beacon.
              </p>
            )}
          

            {/* Quick preset scenarios */}
            <div className="flex flex-col gap-1.5 pt-2 border-t border-[#162733]">
              <span className="text-[10px] text-[#8b98a9] uppercase tracking-wider font-semibold">
                Preset Scenarios (1-Click Test):
              </span>
              <div className="grid grid-cols-1 gap-1">
                {PRESET_IGNITIONS.map((preset) => {
                  const isPresetActive =
                    scenarioIgnition &&
                    Math.abs(scenarioIgnition.lat - preset.lat) < 0.001 &&
                    Math.abs(scenarioIgnition.lng - preset.lng) < 0.001;

                  return (
                    <button
                      key={preset.name}
                      type="button"
                      onClick={() => onSelectIgnition?.({ lat: preset.lat, lng: preset.lng })}
                      disabled={isSubmitting || isRunning}
                      className={`flex items-center justify-between px-2.5 py-1.5 rounded text-left transition-all cursor-pointer ${
                        isPresetActive
                          ? 'bg-[#ff6a2b]/20 border border-[#ff6a2b] shadow-sm'
                          : 'bg-[#121821] hover:bg-[#162733] border border-[#162733] hover:border-[#f5a524]/50'
                      }`}
                    >
                      <div className="flex items-center gap-1.5 min-w-0">
                        {isPresetActive && <span className="text-xs animate-pulse">🔥</span>}
                        <span className={`text-[11px] font-medium truncate ${isPresetActive ? 'text-[#ff6a2b] font-semibold' : 'text-[#e6edf3]'}`}>
                          {preset.name}
                        </span>
                      </div>
                      <span className="text-[10px] text-[#8b98a9] font-mono shrink-0 ml-2">
                        {preset.desc}
                      </span>
                    </button>
                  );
                })}
              </div>
            </div></div>
        )}

        {/* ── 3. Simulation Grid Resolution ──────────────────────── */}
        <div className="px-2.5 py-2 rounded bg-[#0b0f14]/80 border border-[#162733] flex items-center justify-between text-[11px]">
          <span className="text-[#8b98a9] flex items-center gap-1.5">
            <span className="w-1.5 h-1.5 rounded-full bg-[#2ecc71]" />
            Simulation Grid
          </span>
          <span className="font-mono font-medium text-[#e6edf3]">
            90m adaptive <span className="text-[#8b98a9] text-[10px]">(optimized for speed)</span>
          </span>
        </div>

        {/* ── 4. Wind Override (What-If Controls) ────────────────── */}
        <div className="p-2.5 rounded bg-[#0b0f14]/80 border border-[#162733] flex flex-col gap-2.5">
          <div className="flex items-center justify-between">
            <label className="flex items-center gap-2 cursor-pointer select-none">
              <input
                type="checkbox"
                checked={isWindOverrideEnabled}
                onChange={(e) => onToggleWindOverride(e.target.checked)}
                disabled={isSubmitting || isRunning}
                className="w-4 h-4 accent-[#ff6a2b] rounded cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-[#ff6a2b]"
              />
              <span className="text-xs font-semibold text-[#e6edf3]">Wind Override</span>
            </label>

            {isWindOverrideEnabled && (
              <span className="text-[9px] font-mono text-[#f5a524] bg-[#f5a524]/15 px-1.5 py-0.5 rounded font-bold">
                SCENARIO MODE
              </span>
            )}
          </div>

          {isWindOverrideEnabled && (
            <div className="flex flex-col gap-2.5 pt-2 border-t border-[#162733]">
              {/* Wind Speed (0.0 to 40.0 m/s) */}
              <div className="flex flex-col gap-1">
                <div className="flex justify-between text-[11px]">
                  <span className="text-[#8b98a9]">Speed (m/s)</span>
                  <span className="font-mono text-[#e6edf3] font-semibold">{windSpeed.toFixed(1)} m/s</span>
                </div>
                <div className="flex items-center gap-2">
                  <input
                    type="range"
                    min="0"
                    max="40"
                    step="0.5"
                    value={windSpeed}
                    onChange={(e) => onWindSpeedChange(Number(e.target.value))}
                    disabled={isSubmitting || isRunning}
                    className="flex-1 accent-[#ff6a2b] cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-[#ff6a2b] rounded-sm"
                    aria-label="Wind speed in metres per second"
                  />
                  <input
                    type="number"
                    min="0"
                    max="40"
                    step="0.5"
                    value={windSpeed}
                    onChange={(e) => {
                      const v = Math.max(0, Math.min(40, Number(e.target.value)));
                      onWindSpeedChange(v);
                    }}
                    disabled={isSubmitting || isRunning}
                    className="w-14 px-1.5 py-0.5 text-right font-mono text-xs bg-[#121821] border border-[#162733] rounded text-[#e6edf3] focus:outline-none focus-visible:ring-1 focus-visible:ring-[#ff6a2b]"
                    aria-label="Numeric wind speed"
                  />
                </div>
              </div>

              {/* Wind Direction (0 to 360 degrees FROM) */}
              <div className="flex flex-col gap-1">
                <div className="flex justify-between text-[11px]">
                  <span className="text-[#8b98a9]">Direction FROM</span>
                  <span className="font-mono text-[#e6edf3] font-semibold">
                    {Math.round(windDirFrom)}° ({cardinalFromDeg(windDirFrom)})
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  <input
                    type="range"
                    min="0"
                    max="360"
                    step="5"
                    value={windDirFrom}
                    onChange={(e) => onWindDirFromChange(Number(e.target.value))}
                    disabled={isSubmitting || isRunning}
                    className="flex-1 accent-[#ff6a2b] cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-[#ff6a2b] rounded-sm"
                    aria-label="Wind direction from in degrees"
                  />
                  <input
                    type="number"
                    min="0"
                    max="360"
                    step="5"
                    value={windDirFrom}
                    onChange={(e) => {
                      const v = Math.max(0, Math.min(360, Number(e.target.value)));
                      onWindDirFromChange(v);
                    }}
                    disabled={isSubmitting || isRunning}
                    className="w-14 px-1.5 py-0.5 text-right font-mono text-xs bg-[#121821] border border-[#162733] rounded text-[#e6edf3] focus:outline-none focus-visible:ring-1 focus-visible:ring-[#ff6a2b]"
                    aria-label="Numeric wind direction"
                  />
                </div>
                <p className="text-[10px] text-[#657787] font-mono leading-tight">
                  Blows toward {(Math.round(windDirFrom + 180) % 360)}° ({cardinalFromDeg(windDirFrom + 180)})
                </p>
              </div>
            </div>
          )}
        </div>

        {/* ── 5. Submission Error Notice ────────────────────────── */}
        {submissionError && (
          <div className="p-2.5 bg-[#ff3b30]/10 border border-[#ff3b30]/30 rounded text-xs flex flex-col gap-1.5">
            <div className="flex items-start justify-between">
              <span className="font-bold text-[#ff3b30] flex items-center gap-1">
                <span>✕</span> Submission Failed
              </span>
              <button
                onClick={onDismissError}
                className="text-[#8b98a9] hover:text-[#e6edf3]"
                aria-label="Dismiss error"
              >
                ✕
              </button>
            </div>
            <p className="text-[11px] text-[#e6edf3] leading-relaxed">{submissionError}</p>
          </div>
        )}

        {/* ── 6. Job Execution & Live Progress ───────────────────── */}
        {isRunning && (
          <div className="p-2.5 bg-[#121821] border border-[#ff6a2b]/30 rounded flex flex-col gap-2" role="status" aria-live="polite">
            <div className="flex justify-between items-center text-xs">
              <div className="flex items-center gap-1.5 font-medium text-[#e6edf3]">
                <span className="w-2 h-2 rounded-full bg-[#ff6a2b] animate-pulse" />
                <span className="capitalize">{jobData?.status}</span>
                <span className="text-[#8b98a9]">· {jobData?.stage ?? 'Running simulation…'}</span>
              </div>
              <span className="tabular-nums font-mono font-bold text-[#ff6a2b]">
                {progressPct}%
              </span>
            </div>

            <div className="w-full h-1.5 bg-[#162733] rounded-full overflow-hidden">
              <div
                className="h-full bg-gradient-to-r from-[#ff6a2b] to-[#f5a524] rounded-full transition-all duration-300"
                style={{ width: `${progressPct}%` }}
                role="progressbar"
                aria-valuenow={progressPct}
                aria-valuemin={0}
                aria-valuemax={100}
              />
            </div>
          </div>
        )}

        {jobData?.status === 'done' && (
          <div className="p-2 bg-[#2ecc71]/10 border border-[#2ecc71]/30 rounded text-xs flex items-center justify-between text-[#2ecc71]">
            <span className="flex items-center gap-1.5 font-medium">
              <span>✓</span> Simulation Completed
            </span>
            <span className="font-mono text-[10px]">Job #{jobData.job_id.slice(0, 8)}</span>
          </div>
        )}

        {jobData?.status === 'error' && (
          <div className="p-2 bg-[#ff3b30]/10 border border-[#ff3b30]/40 rounded text-xs text-[#ff3b30] flex flex-col gap-1.5">
            <div className="flex items-center gap-1.5 font-bold">
              <span>✕</span> {jobData.error?.code === 'NON_BURNABLE_IGNITION' ? 'Invalid Ignition Location' : 'Simulation Failed'}
            </div>
            <p className="text-[11px] text-[#e6edf3] leading-relaxed">
              {jobData.error?.message || 'An error occurred during simulation processing.'}
            </p>
            {jobData.error?.code === 'NON_BURNABLE_IGNITION' && (
              <div className="pt-1.5 border-t border-[#ff3b30]/20 text-[10px] text-[#f5a524]">
                💡 Non-combustible surface. Please click a green vegetated area on the map or click a preset above!
              </div>
            )}
          </div>
        )}

        {/* ── 7. Submission Action Button ───────────────────────── */}
        <div className="flex flex-col gap-1.5">
          <button
            onClick={onSubmit}
            disabled={!canSubmit || isSubmitting || isRunning}
            className={`w-full py-2.5 min-h-[44px] rounded text-xs font-bold uppercase tracking-wider transition-all shadow-md focus:outline-none focus-visible:ring-2 focus-visible:ring-[#ff6a2b] focus-visible:ring-offset-2 focus-visible:ring-offset-[#121821] ${
              canSubmit && !isSubmitting && !isRunning
                ? 'bg-[#ff6a2b] hover:bg-[#ff854d] text-white cursor-pointer active:scale-[0.99]'
                : 'bg-[#162733] text-[#657787] cursor-not-allowed opacity-60'
            }`}
            aria-busy={isSubmitting || isRunning}
          >
            {isSubmitting
              ? 'Submitting Job…'
              : isRunning
              ? 'Simulation In Progress…'
              : mode === 'LIVE'
              ? '▶ Run Live Simulation'
              : '▶ Run Scenario Simulation'}
          </button>

          {!canSubmit && !isRunning && !isSubmitting && (
            <p className="text-[10px] text-center text-[#8b98a9] leading-tight">
              {mode === 'LIVE'
                ? 'Select a fire cluster above to enable simulation.'
                : 'Place an ignition point on the map to enable scenario.'}
            </p>
          )}
        </div>
      </div>
    </Panel>
  );
}
