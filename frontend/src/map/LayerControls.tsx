/**
 * LayerControls — floating layer visibility toggles for the map workspace.
 */

import { useState } from 'react';
import type { MapLayerVisibility } from './mapTypes';

interface LayerControlsProps {
  visibility: MapLayerVisibility;
  onChange: (visibility: MapLayerVisibility) => void;
}

const LAYER_CONFIG: Array<{ key: keyof MapLayerVisibility; label: string; icon: string; desc: string }> = [
  { key: 'detections', label: 'Fire Detections', icon: '◉', desc: 'NASA FIRMS active fire pixels' },
  { key: 'arrivalBands', label: 'Arrival Bands', icon: '▰', desc: '0–12h fire spread wavefronts' },
  { key: 'settlements', label: 'Settlements', icon: '⬡', desc: 'Threatened villages and towns' },
  { key: 'routes', label: 'Safe Routes', icon: '→', desc: 'Fire-aware evacuation paths' },
  { key: 'baselineRoutes', label: 'Baseline Routes', icon: '⇢', desc: 'Naive paths cut by wildfire' },
];

export function LayerControls({ visibility, onChange }: LayerControlsProps) {
  const [isOpen, setIsOpen] = useState(false);

  const toggle = (key: keyof MapLayerVisibility) => {
    onChange({
      ...visibility,
      [key]: !visibility[key],
    });
  };

  return (
    <div className="relative">
      {/* Toggle button */}
      <button
        onClick={() => setIsOpen((open) => !open)}
        className={`flex items-center gap-1.5 px-2.5 py-1.5 text-[11px] font-semibold tracking-wider uppercase rounded border transition-colors ${
          isOpen
            ? 'bg-[#ff6a2b]/20 border-[#ff6a2b] text-[#ff6a2b]'
            : 'bg-[#121821]/90 backdrop-blur-md border-[#162733] text-[#8b98a9] hover:text-[#e6edf3]'
        }`}
        aria-expanded={isOpen}
        aria-label="Toggle map layer visibility panel"
      >
        <span aria-hidden="true">◫</span>
        <span>Layers</span>
      </button>

      {/* Layer options menu */}
      {isOpen && (
        <div
          className="absolute bottom-full mb-2 left-0 w-56 p-2 bg-[#121821]/95 backdrop-blur-md border border-[#162733] rounded shadow-xl flex flex-col gap-1.5 z-20"
          role="dialog"
          aria-label="Map layers"
        >
          <div className="flex items-center justify-between pb-1 border-b border-[#162733] px-1">
            <span className="text-[10px] font-bold uppercase tracking-wider text-[#8b98a9]">
              Map Layers
            </span>
            <button
              onClick={() => setIsOpen(false)}
              className="text-xs text-[#657787] hover:text-[#e6edf3] p-0.5"
              aria-label="Close layers menu"
            >
              ✕
            </button>
          </div>

          {LAYER_CONFIG.map(({ key, label, icon, desc }) => {
            const active = visibility[key];
            return (
              <label
                key={key}
                className="flex items-start gap-2 p-1.5 rounded hover:bg-[#162733]/50 cursor-pointer select-none transition-colors"
              >
                <input
                  type="checkbox"
                  checked={active}
                  onChange={() => toggle(key)}
                  className="mt-0.5 rounded border-[#162733] text-[#ff6a2b] focus:ring-[#ff6a2b] bg-[#0b0f14]"
                />
                <div className="flex flex-col">
                  <div className="flex items-center gap-1.5">
                    <span className="text-xs text-[#8b98a9]" aria-hidden="true">
                      {icon}
                    </span>
                    <span className={`text-xs font-medium ${active ? 'text-[#e6edf3]' : 'text-[#657787]'}`}>
                      {label}
                    </span>
                  </div>
                  <span className="text-[10px] text-[#657787]">{desc}</span>
                </div>
              </label>
            );
          })}
        </div>
      )}
    </div>
  );
}

