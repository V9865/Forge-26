/**
 * TopBar — compact operations header for EmberRoute.
 *
 * Always visible indicators:
 * - EmberRoute brand
 * - Operating mode (LIVE / SCENARIO)
 * - Wind override indicator
 * - Data freshness
 * - Backend connection status
 * - Simulation status
 * - Responsive drawer toggles for screens below 1024px
 */

import { StatusBadge } from '@/components/StatusBadge';
import { useBackendHealth } from '@/hooks/useBackendHealth';
import { formatAge } from '@/utils/format';
import type { ConnectionStatus, JobStatus, OperatingMode } from '@/types';

interface TopBarProps {
  operatingMode: OperatingMode;
  onModeToggle: () => void;
  modeToggleDisabled?: boolean;
  jobStatus: JobStatus | null;
  jobStage?: string | null;
  isMonitoring: boolean;
  isMonitorLocked?: boolean;
  monitorLockReason?: string;
  windOverrideActive: boolean;
  selectedArea?: string;
  onToggleLeftDrawer?: () => void;
  onToggleRightDrawer?: () => void;
  activeDrawer?: 'left' | 'right' | null;
}

function connectionVariant(status: ConnectionStatus): 'connected' | 'disconnected' | 'connecting' {
  switch (status) {
    case 'CONNECTED':    return 'connected';
    case 'DISCONNECTED':
    case 'ERROR':        return 'disconnected';
    default:             return 'connecting';
  }
}

function connectionLabel(status: ConnectionStatus): string {
  switch (status) {
    case 'CONNECTED':    return 'Backend';
    case 'DISCONNECTED': return 'Offline';
    case 'ERROR':        return 'Error';
    default:             return 'Connecting';
  }
}

export function TopBar({
  operatingMode,
  onModeToggle,
  modeToggleDisabled = false,
  jobStatus,
  jobStage,
  isMonitoring,
  windOverrideActive,
  selectedArea,
  onToggleLeftDrawer,
  onToggleRightDrawer,
  activeDrawer,
}: TopBarProps) {
  const { status: connStatus, lastChecked } = useBackendHealth(30_000);

  return (
    <header
      className="flex items-center justify-between gap-1.5 sm:gap-3 px-2 sm:px-4 border-b border-[#162733] bg-[#0b0f14] z-20 flex-shrink-0 w-full overflow-hidden"
      style={{ height: 'var(--spacing-header, 2.75rem)' }}
      role="banner"
    >
      {/* ── Left section: Drawer toggle (mobile/tablet) + Brand ── */}
      <div className="flex items-center gap-1.5 sm:gap-2.5 flex-shrink-0 min-w-0">
        {/* Mobile/Tablet left panel toggle button (< 1024px) */}
        {onToggleLeftDrawer && (
          <button
            onClick={onToggleLeftDrawer}
            className={`lg:hidden flex items-center justify-center w-7 h-7 rounded border transition-colors ${
              activeDrawer === 'left'
                ? 'border-[#ff6a2b] bg-[#ff6a2b]/20 text-[#ff6a2b]'
                : 'border-[#162733] bg-[#121821] text-[#8b98a9] hover:text-[#e6edf3]'
            }`}
            aria-label="Toggle intelligence and simulation panel"
            title="Intelligence & Simulation"
          >
            <span className="text-xs" aria-hidden="true">◉</span>
          </button>
        )}

        {/* Brand */}
        <div className="flex items-center gap-1.5 sm:gap-2 flex-shrink-0">
          <svg
            width="18"
            height="18"
            viewBox="0 0 20 20"
            fill="none"
            aria-hidden="true"
            className="flex-shrink-0"
          >
            <path
              d="M10 2C10 2 6 7 6 11C6 13.21 7.79 15 10 15C12.21 15 14 13.21 14 11C14 7 10 2 10 2Z"
              fill="#ff6a2b"
            />
            <path
              d="M8 12C8 12 7 11 7 10C7 8.5 8.5 7 10 7C10 7 9 9 10 11C10.67 12.33 12 13 12 13C11.5 13.62 10.8 14 10 14C9.2 14 8.5 13.62 8 13V12Z"
              fill="#ffc080"
              opacity="0.8"
            />
            <path
              d="M7 14.5L5 18H15L13 14.5C12.2 15.44 11.16 16 10 16C8.84 16 7.8 15.44 7 14.5Z"
              fill="#ff6a2b"
              opacity="0.6"
            />
          </svg>
          <span className="text-xs sm:text-sm font-bold tracking-tight text-[#e6edf3]">
            EmberRoute
          </span>
          <span
            className="text-[9px] sm:text-[10px] text-[#8b98a9] font-mono tracking-widest uppercase hidden md:inline"
            aria-label="Wildfire intelligence"
          >
            WILDFIRE INTELLIGENCE
          </span>
        </div>

        {/* Divider */}
        <div className="h-4 w-px bg-[#162733] flex-shrink-0 hidden xs:block" aria-hidden="true" />

        {/* Mode toggle */}
        <button
          onClick={modeToggleDisabled ? undefined : onModeToggle}
          disabled={modeToggleDisabled}
          className={`flex items-center focus:outline-none focus-visible:ring-1 focus-visible:ring-[#ff6a2b] rounded flex-shrink-0 transition-opacity ${
            modeToggleDisabled ? 'opacity-50 cursor-not-allowed pointer-events-none' : 'cursor-pointer'
          }`}
          aria-label={
            modeToggleDisabled
              ? isMonitoring
                ? `Operating mode: ${operatingMode} (locked while autonomous monitoring is active)`
                : `Operating mode: ${operatingMode} (locked during simulation)`
              : `Operating mode: ${operatingMode}. Click to toggle.`
          }
          title={
            modeToggleDisabled
              ? isMonitoring
                ? 'Operating mode locked while autonomous monitoring is active. Stop monitoring first.'
                : 'Mode cannot be changed while a simulation is active'
              : 'Toggle operating mode'
          }
        >
          <StatusBadge
            label={operatingMode}
            variant={operatingMode === 'LIVE' ? 'live' : 'scenario'}
          />
        </button>

        {/* Wind override badge */}
        {windOverrideActive && (
          <span className="hidden sm:inline-flex">
            <StatusBadge label="Wind Override" variant="wind" />
          </span>
        )}

        {/* Selected area */}
        {selectedArea && (
          <span className="hidden xl:flex items-center gap-1 text-xs text-[#8b98a9] truncate max-w-[150px]">
            <span aria-hidden="true" className="text-[#162733]">◈</span>
            <span className="truncate">{selectedArea}</span>
          </span>
        )}
      </div>

      {/* ── Right section: Indicators & Mobile drawer toggle ── */}
      <div className="flex items-center gap-1.5 sm:gap-2 flex-shrink-0">
        {/* Simulation status */}
        {jobStatus && jobStatus !== 'done' && jobStatus !== 'error' && (
          <div className="flex items-center gap-1 text-[10px] sm:text-[11px] text-[#f5a524]">
            <span className="animate-pulse" aria-hidden="true">◉</span>
            <span className="hidden sm:inline">
              {jobStage ? `Sim: ${jobStage}` : 'Simulating…'}
            </span>
          </div>
        )}

        {/* Monitoring indicator */}
        {isMonitoring && (
          <span
            className="hidden sm:flex items-center gap-1 text-[11px] text-[#8b98a9] tracking-wider"
            aria-label="Autonomous monitoring active"
          >
            <span className="animate-pulse text-[#2ecc71]" aria-hidden="true">◉</span>
            <span>Monitor</span>
          </span>
        )}

        {/* Data freshness */}
        <span className="hidden xl:block text-[11px] text-[#657787] font-mono tabular-nums">
          {lastChecked ? formatAge(lastChecked) : '—'}
        </span>

        {/* Connection status */}
        <StatusBadge
          label={connectionLabel(connStatus)}
          variant={connectionVariant(connStatus)}
        />

        {/* Mobile/Tablet right panel toggle button (< 1024px) */}
        {onToggleRightDrawer && (
          <button
            onClick={onToggleRightDrawer}
            className={`lg:hidden flex items-center justify-center w-7 h-7 rounded border transition-colors ${
              activeDrawer === 'right'
                ? 'border-[#ff6a2b] bg-[#ff6a2b]/20 text-[#ff6a2b]'
                : 'border-[#162733] bg-[#121821] text-[#8b98a9] hover:text-[#e6edf3]'
            }`}
            aria-label="Toggle agent and results panel"
            title="Agent & Results"
          >
            <span className="text-xs" aria-hidden="true">◈</span>
          </button>
        )}
      </div>
    </header>
  );
}
