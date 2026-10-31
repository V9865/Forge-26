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

interface MapWorkspaceProps extends MapDataProps {
  isScenarioMode?: boolean;
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

        {/* Empty state guidance when no active simulation results */}
        {!hasData && (
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
          ].map(({ color, label, pattern }) => (
            <div key={label} className="flex items-center gap-2">
              <span style={{ color }} className="text-xs leading-none" aria-hidden="true">
                {pattern}
              </span>
              <span className="text-[10px] text-[#8b98a9] font-mono">{label}</span>
            </div>
          ))}

          <div className="mt-1 pt-1.5 border-t border-[#162733] flex flex-col gap-1">
            <div className="text-[10px] font-bold uppercase tracking-wider text-[#8b98a9]">
              Settlement Status
            </div>
            <div className="flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-[#2ecc71] flex-shrink-0" />
              <span className="text-[10px] text-[#8b98a9]">Evacuate</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-[#ff3b30] flex-shrink-0" />
              <span className="text-[10px] text-[#8b98a9]">Trapped</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-[#8b1a1a] ring-1 ring-white flex-shrink-0" />
              <span className="text-[10px] text-white font-medium">Burning</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-[#657787] flex-shrink-0" />
              <span className="text-[10px] text-[#8b98a9]">Not Threatened</span>
            </div>
          </div>

          <div className="mt-1 pt-1.5 border-t border-[#162733] flex flex-col gap-1">
            <div className="text-[10px] font-bold uppercase tracking-wider text-[#8b98a9]">
              Evacuation Routes
            </div>
            <div className="flex items-center gap-2">
              <span className="text-[#2ecc71] text-xs font-bold leading-none" aria-hidden="true">
                ━━
              </span>
              <span className="text-[10px] text-[#8b98a9]">Fire-aware safe</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-[#ff3b30] text-xs font-bold leading-none" aria-hidden="true">
                ╌╌
              </span>
              <span className="text-[10px] text-[#8b98a9]">Cut by fire</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
