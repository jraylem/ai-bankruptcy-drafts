import React from 'react';

type BillingButtonVariant = 'accent' | 'ghost' | 'primary' | 'secondary';

const billingButtonClassNames: Record<BillingButtonVariant, string> = {
  accent:
    'border border-app-accent/20 bg-app-accent-soft text-app-accent-text hover:border-app-accent/35 hover:bg-app-accent/10 dark:hover:bg-app-accent/25',
  ghost: 'text-text-secondary hover:bg-surface-muted hover:text-text',
  primary: 'bg-app-accent text-white shadow-sm hover:bg-app-accent/90 dark:hover:bg-app-accent/80',
  secondary:
    'border border-border/80 bg-surface-muted text-text-secondary hover:bg-surface hover:text-text',
};

interface BillingButtonProps {
  children: React.ReactNode;
  className?: string;
  disabled?: boolean;
  onClick: () => void;
  variant?: BillingButtonVariant;
}

export const BillingButton: React.FC<BillingButtonProps> = ({
  children,
  className = '',
  disabled = false,
  onClick,
  variant = 'secondary',
}) => (
  <button
    type="button"
    className={`inline-flex h-9 items-center justify-center gap-2 rounded-xl px-3 text-sm font-semibold transition focus:outline-none focus:ring-2 focus:ring-app-accent-soft disabled:cursor-not-allowed disabled:opacity-60 ${billingButtonClassNames[variant]} ${className}`}
    disabled={disabled}
    onClick={onClick}
  >
    {children}
  </button>
);
