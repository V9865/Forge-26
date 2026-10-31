/**
 * Panel — a floating information panel with optional header and collapse.
 */

import { type ReactNode, useState } from 'react';

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

  return (
    <div
      className={`flex flex-col bg-[#121821] border border-[#162733] rounded overflow-hidden ${className}`}
    >
      {/* Header */}
      <div className="flex items-center gap-2 px-3 py-2 border-b border-[#162733] min-h-[36px]">
        {icon && (
          <span className="text-[#ff6a2b] text-sm leading-none" aria-hidden="true">
            {icon}
          </span>
        )}
        <span className="flex-1 text-[11px] font-semibold tracking-widest uppercase text-[#8b98a9]">
          {title}
        </span>
        {headerSlot}
        {collapsible && (
          <button
            onClick={() => setCollapsed((c) => !c)}
            className="ml-auto text-[#8b98a9] hover:text-[#e6edf3] transition-colors w-5 h-5 flex items-center justify-center rounded"
            aria-label={collapsed ? 'Expand panel' : 'Collapse panel'}
            aria-expanded={!collapsed}
          >
            <span aria-hidden="true">{collapsed ? '▸' : '▾'}</span>
          </button>
        )}
      </div>

      {/* Body */}
      {!collapsed && <div className="flex-1 overflow-auto">{children}</div>}
    </div>
  );
}

