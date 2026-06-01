import React from 'react';
import { LuCalendarDays, LuCalendarRange, LuTrendingUp } from 'react-icons/lu';

import type { CostRange, CostsSummaryResponse } from '@/types/costs';

import { formatMoneyDisplay } from './formatting';

interface CostTotalsRowProps {
  data: CostsSummaryResponse;
  range: CostRange;
  /** Rolling-7d weekly total fetched in parallel so we can render
   *  "This week" even when the selected range is 'month'. Null when
   *  range==='week' (the main `data.total_cost_usd` covers it). */
  weeklyTotal: number | null;
}

interface TotalsCardProps {
  label: string;
  value: number | null;
  emphasis?: 'primary' | 'secondary';
  hint?: string;
  icon: React.ReactNode;
}

const TotalsCard: React.FC<TotalsCardProps> = ({
  label,
  value,
  emphasis = 'primary',
  hint,
  icon,
}) => {
  const display = value === null ? '—' : formatMoneyDisplay(value);
  return (
    <article
      className="flex flex-col gap-2 rounded-lg border border-border bg-surface p-5"
      aria-label={`${label}, ${display}`}
    >
      <header className="flex items-center gap-2">
        <span className="flex h-7 w-7 items-center justify-center rounded-md bg-surface-muted text-text-secondary">
          {icon}
        </span>
        <h2 className="text-sm font-semibold text-text-secondary">{label}</h2>
      </header>
      <p
        className={
          emphasis === 'primary'
            ? 'text-3xl font-semibold tabular-nums text-text'
            : 'text-2xl font-semibold tabular-nums text-text-secondary'
        }
      >
        {display}
      </p>
      {hint && <p className="text-xs text-muted">{hint}</p>}
    </article>
  );
};

/**
 * Hero row at the top of the Cost Center page.
 *
 * Three cards, all reading from the same monthly+weekly fetch on
 * CostCenterPage:
 *
 *  - This Week (actual): rolling 7-day total. When range==='month' we
 *    use the side-quest weekly query so the user still sees this number.
 *  - This Month (actual): MTD total. When range==='week' we don't have
 *    this fetched in v1 — falls back to '—' with a hint to switch.
 *  - Projected Month (estimate): linear extrapolation off MTD; null on
 *    range==='week' since weekly→monthly extrapolation is noise.
 *
 * Replaces the old "Forecast" strip which mixed actuals and projections
 * under one ambiguous label.
 */
export const CostTotalsRow: React.FC<CostTotalsRowProps> = ({
  data,
  range,
  weeklyTotal,
}) => {
  const monthTotal = range === 'month' ? data.total_cost_usd : null;
  const weekTotal = range === 'week' ? data.total_cost_usd : weeklyTotal;
  const projectedMonth = data.projection?.this_month_cost_usd ?? null;

  return (
    <section
      aria-label="Spend totals"
      className="mb-6 grid grid-cols-1 gap-4 md:grid-cols-3"
    >
      <TotalsCard
        label="This week"
        value={weekTotal}
        icon={<LuCalendarDays className="h-4 w-4" aria-hidden="true" />}
      />
      <TotalsCard
        label="This month"
        value={monthTotal}
        hint={monthTotal === null ? 'Switch to Month to see MTD' : undefined}
        icon={<LuCalendarRange className="h-4 w-4" aria-hidden="true" />}
      />
      <TotalsCard
        label="Projected month"
        value={projectedMonth}
        emphasis="secondary"
        hint={
          projectedMonth === null
            ? 'Linear projection — Month view only'
            : 'Linear projection from MTD'
        }
        icon={<LuTrendingUp className="h-4 w-4" aria-hidden="true" />}
      />
    </section>
  );
};
