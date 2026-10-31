/**
 * StatusBadge — displays an operating or data status with icon + label.
 * Never uses colour alone.
 */

export type StatusBadgeVariant =
  | 'live'
  | 'scenario'
  | 'wind'
  | 'stale'
  | 'degraded'
  | 'connected'
  | 'disconnected'
  | 'connecting'
  | 'evacuate'
  | 'depart_soon'
  | 'trapped'
  | 'already_burning'
  | 'not_threatened';

interface StatusBadgeProps {
  label: string;
  variant: StatusBadgeVariant;
  className?: string;
}

const VARIANT_STYLES: Record<StatusBadgeVariant, { dot: string; text: string; border: string }> = {
  live:            { dot: 'bg-[#2ecc71]', text: 'text-[#2ecc71]', border: 'border-[#2ecc71]/30' },
  scenario:        { dot: 'bg-[#f5a524]', text: 'text-[#f5a524]', border: 'border-[#f5a524]/30' },
  wind:            { dot: 'bg-[#60a5fa]', text: 'text-[#60a5fa]', border: 'border-[#60a5fa]/30' },
  stale:           { dot: 'bg-[#f5a524]', text: 'text-[#f5a524]', border: 'border-[#f5a524]/30' },
  degraded:        { dot: 'bg-[#ff3b30]', text: 'text-[#ff3b30]', border: 'border-[#ff3b30]/30' },
  connected:       { dot: 'bg-[#2ecc71]', text: 'text-[#8b98a9]', border: 'border-[#162733]' },
  disconnected:    { dot: 'bg-[#ff3b30]', text: 'text-[#ff3b30]', border: 'border-[#ff3b30]/30' },
  connecting:      { dot: 'bg-[#f5a524]', text: 'text-[#8b98a9]', border: 'border-[#162733]' },
  // Evacuation statuses
  evacuate:        { dot: 'bg-[#2ecc71]', text: 'text-[#2ecc71]', border: 'border-[#2ecc71]/30' },
  depart_soon:     { dot: 'bg-[#f5a524]', text: 'text-[#f5a524]', border: 'border-[#f5a524]/30' },
  trapped:         { dot: 'bg-[#ff3b30]', text: 'text-[#ff3b30]', border: 'border-[#ff3b30]/30' },
  // ALREADY BURNING uses #8b1a1a with white ring for high-contrast visibility on dark backgrounds
  already_burning: { dot: 'bg-[#8b1a1a] ring-1 ring-white', text: 'text-white', border: 'border-[#8b1a1a] ring-1 ring-white/80' },
  not_threatened:  { dot: 'bg-[#657787]', text: 'text-[#657787]', border: 'border-[#657787]/30' },
};

export function StatusBadge({ label, variant, className = '' }: StatusBadgeProps) {
  const styles = VARIANT_STYLES[variant];
  return (
    <span
      className={`inline-flex items-center gap-1.5 px-2 py-0.5 text-[11px] font-semibold tracking-widest uppercase border rounded ${styles.text} ${styles.border} ${className}`}
      style={{ background: 'rgba(18,24,33,0.7)' }}
    >
      <span
        className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${styles.dot} ${variant === 'connecting' ? 'animate-pulse' : ''}`}
        aria-hidden="true"
      />
      {label}
    </span>
  );
}
