/**
 * MapWorkspace — the primary map workspace container.
 *
 * Integrates MapView, LayerControls, TimeSlider, and arrival-band legend.
 * Consumes real GeoJSON FeatureCollections directly.
 */

import { useState } from 'react';
import { MapView } from './MapView';
import { LayerControls } from './LayerControls';
import { TimeSlider } from './TimeSlider';
import { DEFAULT_LAYER_VISIBILITY, type MapDataProps, type MapLayerVisibility } from './mapTypes';
import type { ErrorDetail, JobStatus } from '@/types';

interface MapWorkspaceProps extends MapDataProps {
  isScenarioMode?: boolean;
  jobStatus?: JobStatus | null;
  jobError?: ErrorDetail | null;
}

export function MapWorkspace({
  detections = null,
  arrivalBands = null,
  settlements = null,
  routes = null,
  naiveCutSegments = null,
  selectedSettlementId,
  onSelectSettlement,
  scenarioIgnition,
  onSelectIgnition,
  isScenarioMode = false,
  focusAoi = null,
  onBoundsChange,
  jobStatus = null,
  jobError = null,
}: MapWorkspaceProps) {
  const [visibility, setVisibility] = useState<MapLayerVisibility>(DEFAULT_LAYER_VISIBILITY);
  const [timeFilterHours, setTimeFilterHours] = useState<number>(12);

  const hasData =
    (detections?.features?.length ?? 0) > 0 ||
    (arrivalBands?.features?.length ?? 0) > 0 ||
    (settlements?.features?.length ?? 0) > 0 ||
    (routes?.features?.length ?? 0) > 0 ||
    (naiveCutSegments?.features?.length ?? 0) > 0 ||
    (isScenarioMode && Boolean(scenarioIgnition));

  const hasArrivalBands = (arrivalBands?.features?.length ?? 0) > 0;

  return (
    <div
      className="relative flex-1 min-h-0 min-w-0 bg-[#0d1318] overflow-hidden flex flex-col"
      role="region"
      aria-label="Fire intelligence interactive map"
    >
      {/* MapLibre Canvas View */}
      <div className="relative flex-1 min-h-0 w-full">
        <MapView
          detections={detections}
          arrivalBands={arrivalBands}
          settlements={settlements}
          routes={routes}
          naiveCutSegments={naiveCutSegments}
          selectedSettlementId={selectedSettlementId}
          onSelectSettlement={onSelectSettlement}
          scenarioIgnition={scenarioIgnition}
          onSelectIgnition={onSelectIgnition}
          isScenarioMode={isScenarioMode}
          focusAoi={focusAoi}
          onBoundsChange={onBoundsChange}
          visibility={visibility}
          timeFilterHours={timeFilterHours}
        />

        {/* Floating Ignition Beacon Confirmation */}
        {isScenarioMode && scenarioIgnition && !hasArrivalBands && jobStatus !== 'error' && (
          <div className="absolute top-3 left-1/2 -translate-x-1/2 z-20 flex items-center gap-2 px-3 py-1.5 bg-[#121821]/95 backdrop-blur-md border border-[#f5a524]/60 rounded-full shadow-xl pointer-events-auto">
            <span className="w-2 h-2 rounded-full bg-[#f5a524] animate-ping" />
            <span className="text-xs text-[#e6edf3] font-medium">
              Ignition Beacon: <span className="font-mono text-[#f5a524] font-bold">{scenarioIgnition.lat.toFixed(4)}°N, {scenarioIgnition.lng.toFixed(4)}°E</span>
            </span>
          </div>
        )}

        {/* Prominent floating alert if simulation fails (e.g. non-burnable fuel) */}
        {jobStatus === 'error' && jobError && (
          <div className="absolute top-4 left-1/2 -translate-x-1/2 z-30 flex items-start gap-3 max-w-lg w-[92%] p-3.5 bg-[#140b0e]/95 backdrop-blur-md border border-[#ff3b30]/80 rounded-lg shadow-2xl text-left pointer-events-auto animate-fade-in">
            <span className="text-[#ff3b30] text-lg leading-none mt-0.5">⚠️</span>
            <div className="flex-1 min-w-0">
              <span className="text-xs font-bold text-[#ff3b30] uppercase tracking-wider block">
                {jobError.code === 'NON_BURNABLE_IGNITION' ? 'Invalid Ignition Spot' : 'Simulation Refused'}
              </span>
              <p className="text-xs text-[#e6edf3] mt-1 leading-relaxed">
                {jobError.message}
              </p>
              {jobError.code === 'NON_BURNABLE_IGNITION' && (
                <div className="mt-2 pt-2 border-t border-[#ff3b30]/25 text-[11px] text-[#f5a524]">
                  💡 <strong>Terrain Rule:</strong> The selected location is on non-burnable surface (water, city concrete, or bare rock). Fire spread requires combustible vegetation (forest, shrubland, or grass). Click a green area on the map or use a 1-click preset.
                </div>
              )}
            </div>
          </div>
        )}

        {/* Empty state guidance when no active simulation results */}
        {!hasData && !jobError && (
          <div className="absolute top-14 left-1/2 -translate-x-1/2 pointer-events-none z-10 px-3 py-1.5 bg-[#121821]/80 backdrop-blur-md border border-[#162733] rounded text-center max-w-sm shadow-lg">
            <p className="text-xs font-medium text-[#e6edf3]">
              {isScenarioMode ? 'Scenario Mode Active' : 'Live Operations Ready'}
            </p>
            <p className="text-[11px] text-[#8b98a9] mt-0.5">
              {isScenarioMode
                ? 'Click anywhere on the map to place an ignition point.'
                : 'Select an active fire cluster or run a simulation to load spread wavefronts.'}
            </p>
          </div>
        )}

        {/* Bottom Floating Bar: Layer Controls & Time Slider */}
        <div className="absolute bottom-4 left-4 z-10 flex flex-wrap items-center gap-2 max-w-[calc(100%-2rem)]">
          <LayerControls visibility={visibility} onChange={setVisibility} />
          {hasArrivalBands && (
            <TimeSlider
              maxHours={12}
              value={timeFilterHours}
              onChange={setTimeFilterHours}
            />
          )}
        </div>

        {/* Map Legend (Bottom Right) */}
        <div
          className="absolute bottom-4 right-4 z-10 bg-[#121821]/90 backdrop-blur-md border border-[#162733] rounded p-2.5 flex flex-col gap-1.5 shadow-xl select-none"
          aria-label="Map legend"
        >
          <div className="text-[10px] font-bold uppercase tracking-wider text-[#8b98a9] pb-0.5 border-b border-[#162733]">
            Arrival Bands
          </div>
          {[
            { color: '#ff3b30', label: '0–2h wavefront (≤120m)', pattern: '█' },
            { color: '#ff8a00', label: '2–4h wavefront (≤240m)', pattern: '█' },
            { color: '#ffc400', label: '4–8h wavefront (≤480m)', pattern: '█' },
            { color: '#ffe58a', label: '8–12h wavefront (≤720m)', pattern: '█' },
          ].map(({ color, label }) => (
            <div key={label} className="flex items-center gap-2 text-[10px]">
              <span className="inline-block w-3 h-2 rounded-xs" style={{ backgroundColor: color }} />
              <span className="text-[10px] text-[#8b98a9] font-mono">{label}</span>
            </div>
          ))}

          <div className="text-[10px] font-bold uppercase tracking-wider text-[#8b98a9] pt-1 pb-0.5 border-b border-[#162733]">
            Settlement Status
          </div>
          {[
            { color: '#2ecc71', label: 'Evacuate' },
            { color: '#ff3b30', label: 'Trapped' },
            { color: '#ffffff', label: 'Burning', ring: true },
            { color: '#657787', label: 'Not Threatened' },
          ].map(({ color, label, ring }) => (
            <div key={label} className="flex items-center gap-2 text-[10px]">
              {ring ? (
                <span className="inline-block w-2.5 h-2.5 rounded-full border border-white bg-transparent" />
              ) : (
                <span className="inline-block w-2 h-2 rounded-full" style={{ backgroundColor: color }} />
              )}
              <span className="text-[10px] text-[#8b98a9]">{label}</span>
            </div>
          ))}

          <div className="text-[10px] font-bold uppercase tracking-wider text-[#8b98a9] pt-1 pb-0.5 border-b border-[#162733]">
            Evacuation Routes
          </div>
          <div className="flex items-center gap-2 text-[10px]">
            <span className="text-[#2ecc71] text-xs font-bold leading-none" aria-hidden="true">
              —
            </span>
            <span className="text-[10px] text-[#8b98a9]">Fire-aware safe</span>
          </div>
          <div className="flex items-center gap-2 text-[10px]">
            <span className="text-[#ff3b30] text-xs font-bold leading-none" aria-hidden="true">
              —
            </span>
            <span className="text-[10px] text-[#8b98a9]">Cut by fire</span>
          </div>
        </div>
      </div>
    </div>
  );
}
