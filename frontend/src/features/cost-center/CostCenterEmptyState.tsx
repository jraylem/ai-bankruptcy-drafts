import React from 'react';

/** Empty state — replaces the chart row (the KPI cards above still
 *  render at $0). Don't render flat-line charts; they read as broken. */
export const CostCenterEmptyState: React.FC = () => (
  <section className="rounded-lg border border-dashed border-border bg-surface px-6 py-12 text-center">
    <p className="text-sm font-semibold text-text-secondary">
      No spend recorded in the selected range
    </p>
    <p className="mx-auto mt-1 max-w-md text-xs text-muted">
      Start drafting or running cases and the breakdown + daily trend will
      appear here.
    </p>
  </section>
);
