import React from 'react';

type SettingsActionIconButtonProps = {
  'aria-label': string;
  children: React.ReactNode;
  className?: string;
  disabled?: boolean;
  label: string;
  onClick: () => void;
  tooltipAlign?: 'center' | 'end';
};

export const SettingsActionIconButton = ({
  'aria-label': ariaLabel,
  children,
  className = 'hover:bg-surface-muted hover:text-app-accent-text',
  disabled = false,
  label,
  onClick,
  tooltipAlign = 'center',
}: SettingsActionIconButtonProps) => (
  <span className="group relative inline-flex">
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={`rounded-xl p-2 text-muted transition disabled:cursor-wait disabled:opacity-60 ${className}`}
      aria-label={ariaLabel}
    >
      {children}
    </button>
    <span
      className={`pointer-events-none absolute -top-8 z-20 whitespace-nowrap rounded-md border border-border/70 bg-surface px-2 py-1 text-[11px] font-medium text-text opacity-0 shadow-sm transition-opacity duration-150 group-hover:opacity-100 group-focus-within:opacity-100 ${
        tooltipAlign === 'end' ? 'right-0' : 'left-1/2 -translate-x-1/2'
      }`}
    >
      {label}
    </span>
  </span>
);
