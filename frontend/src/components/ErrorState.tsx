/**
 * ErrorState — displays a typed API error with a recovery suggestion.
 */

import type { ApiErrorCode } from '@/types';

interface ErrorStateProps {
  code?: ApiErrorCode | string;
  message?: string;
  onRetry?: () => void;
}

const ERROR_COPY: Partial<Record<ApiErrorCode, { heading: string; detail: string; suggestion: string }>> = {
  NO_FIRE:        { heading: 'No Fire Detections', detail: 'No usable active-fire detections were found in the selected area and time window.', suggestion: 'Try a different area, extend the time window, or switch to Scenario mode.' },
  FEED_DOWN:      { heading: 'Live Feed Unavailable', detail: 'The NASA FIRMS live feed is currently unreachable.', suggestion: 'Data may be stale. Check feed status or try again shortly.' },
  OSM_EMPTY:      { heading: 'Map Data Unavailable', detail: 'Required geographical data (roads, settlements) could not be retrieved from OpenStreetMap.', suggestion: 'The area may have limited OSM coverage. Try a different region.' },
  GRID_TOO_LARGE: { heading: 'Area Too Large', detail: 'The selected area of interest is too large for the chosen resolution.', suggestion: 'Reduce the area or choose a coarser resolution (90m or 120m).' },
  NO_SETTLEMENTS: { heading: 'No Settlements Found', detail: 'No settlements were identified in the selected area.', suggestion: 'Try a wider area or a different region.' },
  BAD_INPUT:      { heading: 'Invalid Input', detail: 'The request contained invalid parameters.', suggestion: 'Review your inputs and try again.' },
  NEEDS_SCENARIO: { heading: 'Switch to Scenario Mode', detail: 'This configuration requires Scenario mode.', suggestion: 'Switch to Scenario mode and place an ignition point on the map.' },
  INTERNAL:       { heading: 'Server Error', detail: 'An internal error occurred on the backend.', suggestion: 'This is not your fault. Please try again or report the issue.' },
};

export function ErrorState({ code, message, onRetry }: ErrorStateProps) {
  const copy = code ? ERROR_COPY[code as ApiErrorCode] : undefined;

  return (
    <div className="flex flex-col gap-2 p-4">
      <div className="flex items-start gap-2">
        <span className="text-[#ff3b30] text-sm mt-0.5" aria-hidden="true">⚠</span>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-semibold text-[#e6edf3]">
            {copy?.heading ?? 'Error'}
          </p>
          {code && (
            <p className="text-[10px] font-mono text-[#657787] mt-0.5 uppercase tracking-wider">
              {code}
            </p>
          )}
        </div>
      </div>

      <p className="text-xs text-[#8b98a9] leading-relaxed">
        {copy?.detail ?? message ?? 'An unexpected error occurred.'}
      </p>

      {copy?.suggestion && (
        <p className="text-xs text-[#657787] leading-relaxed border-l-2 border-[#162733] pl-2">
          {copy.suggestion}
        </p>
      )}

      {onRetry && (
        <button
          onClick={onRetry}
          className="mt-1 self-start text-xs text-[#ff6a2b] hover:text-[#ff8a4a] underline underline-offset-2 transition-colors"
        >
          Try again
        </button>
      )}
    </div>
  );
}

