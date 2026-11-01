import { useState } from 'react';

export function MapLegend() {
  const [isExpanded, setIsExpanded] = useState(true);

  return (
    <div className="bg-[#121821]/95 backdrop-blur-md border border-[#162733] rounded-lg shadow-xl text-[11px] overflow-hidden max-w-xs transition-all pointer-events-auto">
      {/* Header with collapse toggle */}
      <div
        onClick={() => setIsExpanded((prev) => !prev)}
        className="flex items-center justify-between px-3 py-2 border-b border-[#162733] cursor-pointer hover:bg-[#162733]/50 select-none"
      >
        <span className="text-[10px] font-bold uppercase tracking-wider text-[#8b98a9] flex items-center gap-1.5">
          <span className="w-1.5 h-1.5 rounded-full bg-[#ff6a2b]" />
          Operational Legend
        </span>
        <button
          type="button"
          className="text-xs text-[#657787] hover:text-[#e6edf3] transition-colors"
          aria-label={isExpanded ? 'Collapse legend' : 'Expand legend'}
        >
          {isExpanded ? '▾' : '▸'}
        </button>
      </div>

      {isExpanded && (
        <div className="p-3 flex flex-col gap-3 max-h-72 overflow-y-auto">
          {/* 1. Fire Wavefront Arrival Bands */}
          <div>
            <div className="text-[9px] uppercase tracking-wider font-semibold text-[#8b98a9] mb-1.5">
              Fire Wavefront Arrival
            </div>
            <div className="grid grid-cols-2 gap-1.5 font-mono text-[10px]">
              <div className="flex items-center gap-1.5">
                <span className="w-3 h-3 rounded-xs bg-[#ff3b30] shrink-0 border border-black/40" />
                <span className="text-[#e6edf3]">0–2h (&lt;120m)</span>
              </div>
              <div className="flex items-center gap-1.5">
                <span className="w-3 h-3 rounded-xs bg-[#ff8a00] shrink-0 border border-black/40" />
                <span className="text-[#e6edf3]">2–4h (&lt;240m)</span>
              </div>
              <div className="flex items-center gap-1.5">
                <span className="w-3 h-3 rounded-xs bg-[#ffc400] shrink-0 border border-black/40" />
                <span className="text-[#e6edf3]">4–8h (&lt;480m)</span>
              </div>
              <div className="flex items-center gap-1.5">
                <span className="w-3 h-3 rounded-xs bg-[#ffe58a] shrink-0 border border-black/40" />
                <span className="text-[#e6edf3]">8–12h (&lt;720m)</span>
              </div>
            </div>
          </div>

          {/* 2. Settlements & Shelters */}
          <div className="pt-2 border-t border-[#162733]">
            <div className="text-[9px] uppercase tracking-wider font-semibold text-[#8b98a9] mb-1.5">
              Settlement Status
            </div>
            <div className="flex flex-col gap-1 text-[10px]">
              <div className="flex items-center gap-2">
                <span className="w-2.5 h-2.5 rounded-full bg-[#2ecc71] shrink-0 shadow-xs" />
                <span className="text-[#e6edf3]">EVACUATE (Safe route found)</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="w-2.5 h-2.5 rounded-full bg-[#ff3b30] shrink-0 shadow-xs" />
                <span className="text-[#e6edf3]">TRAPPED (Routes severed)</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="w-2.5 h-2.5 rounded-full bg-[#8b1a1a] border border-white shrink-0 shadow-xs" />
                <span className="text-[#e6edf3]">ALREADY BURNING</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="w-2.5 h-2.5 rounded-full bg-[#657787] shrink-0" />
                <span className="text-[#8b98a9]">NOT THREATENED</span>
              </div>
            </div>
          </div>

          {/* 3. Evacuation Routes */}
          <div className="pt-2 border-t border-[#162733]">
            <div className="text-[9px] uppercase tracking-wider font-semibold text-[#8b98a9] mb-1.5">
              Evacuation Routes
            </div>
            <div className="flex flex-col gap-1.5 text-[10px]">
              <div className="flex items-center gap-2">
                <div className="w-6 h-1 rounded bg-[#00e676] shadow-[0_0_8px_#00ff88]" />
                <span className="text-[#00e676] font-medium">Fire-aware recommended route</span>
              </div>
              <div className="flex items-center gap-2">
                <div className="w-6 h-0.5 border-t-2 border-dashed border-[#ff1744]" />
                <span className="text-[#ff1744] font-medium">Baseline segment cut by fire</span>
              </div>
            </div>
          </div>

          {/* 4. Weather & FIRMS Hotspots */}
          <div className="pt-2 border-t border-[#162733]">
            <div className="text-[9px] uppercase tracking-wider font-semibold text-[#8b98a9] mb-1.5">
              Environmental Overlays
            </div>
            <div className="flex flex-col gap-1 text-[10px]">
              <div className="flex items-center gap-2">
                <span className="text-xs text-[#00d2ff]">➤</span>
                <span className="text-[#00d2ff]">Wind vector (direction & speed)</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="w-2.5 h-2.5 rounded-full bg-[#ff6a2b] shrink-0" />
                <span className="text-[#ff6a2b]">NASA FIRMS active detection</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-xs">🔥</span>
                <span className="text-[#f5a524]">Scenario ignition beacon</span>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
