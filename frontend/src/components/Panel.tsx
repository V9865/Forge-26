/**
 * Panel — a floating information panel with optional header and collapse.
 */

import { type ReactNode, useId, useState } from 'react';

interface PanelProps {
  title: string;
  icon?: string;
  children: ReactNode;
  collapsible?: boolean;
  defaultCollapsed?: boolean;
  className?: string;
  headerSlot?: ReactNode;
}

export function Panel({
  title,
  icon,
  children,
  collapsible = false,
  defaultCollapsed = false,
  className = '',
  headerSlot,
}: PanelProps) {
  const [collapsed, setCollapsed] = useState(defaultCollapsed);
  const reactId = useId();
  const bodyId = `panel-body-${reactId}`;

  return (
    <div
      className={`flex flex-col flex-shrink-0 w-full bg-[#121821] border border-[#162733] rounded-lg overflow-hidden shadow-sm transition-all duration-150 ${className}`}
    >
      {/* Header */}
      <div
        className={`flex items-center gap-2 px-3 py-2 border-b border-[#162733] min-h-[38px] ${
          collapsible ? 'cursor-pointer select-none hover:bg-[#162733]/50 transition-colors' : ''
        }`}
        onClick={collapsible ? () => setCollapsed((c) => !c) : undefined}
      >
        {icon && (
          <span className="text-[#ff6a2b] text-sm leading-none shrink-0" aria-hidden="true">
            {icon}
          </span>
        )}
        <span className="flex-1 text-[11px] font-semibold tracking-widest uppercase text-[#8b98a9] truncate">
          {title}
        </span>
        {headerSlot && (
          <div onClick={(e) => e.stopPropagation()} className="shrink-0 flex items-center">
            {headerSlot}
          </div>
        )}
        {collapsible && (
          <button
            onClick={(e) => {
              e.stopPropagation();
              setCollapsed((c) => !c);
            }}
            className="ml-auto text-[#8b98a9] hover:text-[#e6edf3] transition-colors w-7 h-7 flex items-center justify-center rounded focus:outline-none focus-visible:ring-1 focus-visible:ring-[#ff6a2b]"
            aria-label={collapsed ? `Expand ${title} panel` : `Collapse ${title} panel`}
            aria-expanded={!collapsed}
            aria-controls={bodyId}
          >
            <span aria-hidden="true" className="text-xs">{collapsed ? '▸' : '▾'}</span>
          </button>
        )}
      </div>

      {/* Body */}
      {!collapsed && (
        <div id={bodyId} role="region" aria-label={title} className="flex-1">
          {children}
        </div>
      )}
    </div>
  );
}
