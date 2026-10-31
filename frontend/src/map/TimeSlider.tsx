/**
 * TimeSlider — interactive fire spread progression controller (0 to 12 hours).
 */

interface TimeSliderProps {
  maxHours: number;
  value: number;
  onChange: (hours: number) => void;
  disabled?: boolean;
}

export function TimeSlider({ maxHours = 12, value, onChange, disabled = false }: TimeSliderProps) {
  return (
    <div
      className="flex items-center gap-2.5 px-3 py-1.5 bg-[#121821]/90 backdrop-blur-md border border-[#162733] rounded shadow-lg max-w-sm w-full"
      role="region"
      aria-label="Simulation time progression slider"
    >
      <div className="flex items-center gap-1 flex-shrink-0">
        <span className="text-[10px] uppercase font-bold tracking-wider text-[#8b98a9]">
          Time:
        </span>
        <span className="text-xs font-mono tabular-nums text-[#ff6a2b] font-semibold min-w-[3.5ch]">
          {value === 12 ? 'All' : `+${value}h`}
        </span>
      </div>

      <input
        type="range"
        min={0}
        max={maxHours}
        step={0.5}
        value={value}
        disabled={disabled}
        onChange={(e) => onChange(parseFloat(e.target.value))}
        className="flex-1 h-1.5 bg-[#162733] rounded-lg appearance-none cursor-pointer accent-[#ff6a2b] disabled:opacity-40 disabled:cursor-not-allowed"
        aria-label="Fire arrival time filter"
      />

      <div className="flex items-center gap-1 flex-shrink-0 text-[10px] text-[#657787] font-mono">
        <span>0h</span>
        <span>…</span>
        <span>{maxHours}h</span>
      </div>
    </div>
  );
}

