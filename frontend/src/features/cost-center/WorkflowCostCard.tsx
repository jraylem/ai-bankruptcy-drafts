import React from 'react';

import type { WorkflowCountUnit, WorkflowMetricEntry } from '@/types/costs';

import { formatMoneyDisplay, formatMoneyOrTiny } from './formatting';

interface WorkflowCostCardProps {
  title: string;
  icon: React.ReactNode;
  totalUsd: number;
  metrics: WorkflowMetricEntry[];
  /** Tooltip text explaining what kinds are included. */
  includesHint: string;
}

const pluralize = (unit: WorkflowCountUnit, count: number): string => {
  if (count === 1) return unit;
  switch (unit) {
    case 'session': return 'sessions';
    case 'message': return 'messages';
    case 'run': return 'runs';
    case 'case': return 'cases';
    default: return `${unit}s`;
  }
};

/** Picks the primary entry for the "no activity yet" empty-state copy. */
const primaryEmptyUnit = (metrics: WorkflowMetricEntry[]): WorkflowCountUnit => {
  if (metrics.length === 0) return 'session';
  // Preference order: run > session > case > message — pick the most
  // representative unit for the empty-state hint.
  const order: WorkflowCountUnit[] = ['run', 'session', 'case', 'message'];
  for (const u of order) {
    if (metrics.some((m) => m.unit === u)) return u;
  }
  return metrics[0].unit;
};

export const WorkflowCostCard: React.FC<WorkflowCostCardProps> = ({
  title,
  icon,
  totalUsd,
  metrics,
  includesHint,
}) => {
  const total = formatMoneyDisplay(totalUsd);
  const allZero = metrics.every((m) => m.count === 0);

  return (
    <article
      className="flex flex-col gap-3 rounded-lg border border-border bg-surface p-5"
      aria-label={`${title}, total ${total}`}
    >
      <header className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <span className="flex h-7 w-7 items-center justify-center rounded-md bg-surface-muted text-text-secondary">
            {icon}
          </span>
          <h2
            className="text-sm font-semibold text-text-secondary"
            title={includesHint}
          >
            {title}
          </h2>
        </div>
      </header>
      <p className="text-2xl font-semibold tabular-nums text-text-secondary">
        {total}
      </p>
      {allZero ? (
        <p className="text-xs text-muted">
          No {pluralize(primaryEmptyUnit(metrics), 0)} yet
        </p>
      ) : (
        <ul className="flex flex-col gap-1 text-xs text-muted">
          {metrics.map((m) => (
            <li
              key={m.unit}
              className="flex items-baseline gap-2"
            >
              <span className="font-semibold text-text-secondary tabular-nums">
                {formatMoneyOrTiny(m.avg_cost_usd)}
              </span>
              <span>avg / {m.unit}</span>
              <span aria-hidden="true">·</span>
              <span className="tabular-nums">
                {m.count} {pluralize(m.unit, m.count)}
              </span>
            </li>
          ))}
        </ul>
      )}
    </article>
  );
};
