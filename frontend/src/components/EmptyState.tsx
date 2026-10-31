/**
 * EmptyState — displayed when a panel has no data to show.
 */

interface EmptyStateProps {
  icon?: string;
  title: string;
  description?: string;
  action?: { label: string; onClick: () => void };
}

export function EmptyState({ icon, title, description, action }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 py-8 px-4 text-center">
      {icon && (
        <span className="text-3xl text-[#162733] mb-1" aria-hidden="true">
          {icon}
        </span>
      )}
      <p className="text-sm font-medium text-[#8b98a9]">{title}</p>
      {description && (
        <p className="text-xs text-[#657787] max-w-[22ch] leading-relaxed">{description}</p>
      )}
      {action && (
        <button
          onClick={action.onClick}
          className="mt-2 text-xs text-[#ff6a2b] hover:text-[#ff8a4a] underline underline-offset-2 transition-colors"
        >
          {action.label}
        </button>
      )}
    </div>
  );
}

