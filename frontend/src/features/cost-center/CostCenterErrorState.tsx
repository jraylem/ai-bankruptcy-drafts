import React, { useEffect, useRef } from 'react';

interface CostCenterErrorStateProps {
  onRetry: () => void;
}

/**
 * Error state — single card replacing the chart row. Auto-focuses the
 * Try again button so keyboard users can hit Enter immediately. KPI
 * values are deliberately NOT rendered from a partial response — we
 * don't want stale $ numbers misleading anyone after a failure.
 */
export const CostCenterErrorState: React.FC<CostCenterErrorStateProps> = ({
  onRetry,
}) => {
  const ref = useRef<HTMLButtonElement | null>(null);
  useEffect(() => {
    ref.current?.focus();
  }, []);

  return (
    <section className="rounded-lg border border-app-danger-soft bg-app-danger-soft/40 px-6 py-10 text-center">
      <p className="text-sm font-semibold text-text-secondary">
        Couldn't load cost data
      </p>
      <p className="mx-auto mt-1 max-w-md text-xs text-muted">
        Something went wrong fetching your firm's usage. This is usually
        transient.
      </p>
      <button
        ref={ref}
        type="button"
        onClick={onRetry}
        className="mt-4 inline-flex items-center gap-1.5 rounded-md border border-border bg-surface px-3 py-1.5 text-xs font-semibold text-text-secondary hover:border-app-accent-soft hover:text-app-accent-text focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-app-accent"
      >
        Try again
      </button>
    </section>
  );
};
