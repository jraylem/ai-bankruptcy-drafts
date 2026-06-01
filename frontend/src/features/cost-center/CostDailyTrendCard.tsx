import React, { useMemo } from 'react';
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

import type { DailyCostEntry } from '@/types/costs';

import { formatMoney } from './formatting';

interface CostDailyTrendCardProps {
  series: DailyCostEntry[];
}

/**
 * Daily cost trend — recharts area chart, 200px desktop / 160px mobile.
 * Line chart with a soft accent fill below: communicates "rate of change"
 * better than bars, which is what users actually want to know
 * ("is spend trending up?"). The accessible name reflects the range
 * and extremes so screen readers get the gist without reading
 * point-by-point.
 *
 * A visually-hidden <dl> mirrors the underlying datapoints so assistive
 * tech can navigate the exact values when needed.
 */
export const CostDailyTrendCard: React.FC<CostDailyTrendCardProps> = ({
  series,
}) => {
  const points = useMemo(
    () =>
      series.map((d) => ({
        // recharts wants primitive keys; keep raw ISO in a sibling.
        day: new Date(d.day).toLocaleDateString(undefined, {
          month: 'short',
          day: 'numeric',
        }),
        iso: d.day,
        cost: d.cost_usd,
      })),
    [series],
  );

  const { min, max, total } = useMemo(() => {
    if (points.length === 0) return { min: 0, max: 0, total: 0 };
    let mn = points[0].cost;
    let mx = points[0].cost;
    let t = 0;
    for (const p of points) {
      if (p.cost < mn) mn = p.cost;
      if (p.cost > mx) mx = p.cost;
      t += p.cost;
    }
    return { min: mn, max: mx, total: t };
  }, [points]);

  const ariaLabel =
    points.length === 0
      ? 'Daily spend trend — no data'
      : `Daily spend trend over ${points.length} days, ranging from ${formatMoney(min)} to ${formatMoney(max)}, total ${formatMoney(total)}`;

  return (
    <section
      role="region"
      aria-label={ariaLabel}
      className="flex flex-col gap-4 rounded-lg border border-border bg-surface p-5"
    >
      <h2 className="text-sm font-semibold text-text-secondary">Daily spend</h2>
      <div className="h-[200px] w-full max-sm:h-[160px]">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart
            data={points}
            margin={{ top: 8, right: 8, bottom: 0, left: 0 }}
          >
            <defs>
              <linearGradient id="cost-area" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="rgb(99 102 241)" stopOpacity={0.35} />
                <stop offset="100%" stopColor="rgb(99 102 241)" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid
              vertical={false}
              stroke="rgba(0,0,0,0.05)"
            />
            <XAxis
              dataKey="day"
              tick={{ fontSize: 10, fill: 'currentColor' }}
              tickLine={false}
              axisLine={false}
              interval="preserveStartEnd"
              minTickGap={24}
            />
            <YAxis
              hide
              domain={[0, (dataMax: number) => (dataMax === 0 ? 1 : dataMax * 1.1)]}
            />
            <Tooltip
              cursor={{ stroke: 'rgba(99, 102, 241, 0.5)', strokeDasharray: '2 2' }}
              contentStyle={{
                fontSize: 12,
                padding: '6px 10px',
                borderRadius: 8,
                border: '1px solid var(--color-border, #e5e7eb)',
              }}
              formatter={(v) => formatMoney(Number(v ?? 0))}
              labelFormatter={(label) => String(label ?? '')}
            />
            <Area
              type="monotone"
              dataKey="cost"
              stroke="rgb(99 102 241)"
              strokeWidth={2}
              fill="url(#cost-area)"
              isAnimationActive={false}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
      {/* Screen-reader fallback for the chart — every datapoint as a
          definition list, hidden from sighted users. */}
      <dl className="sr-only">
        {points.map((p) => (
          <React.Fragment key={p.iso}>
            <dt>{new Date(p.iso).toLocaleDateString()}</dt>
            <dd>{formatMoney(p.cost)}</dd>
          </React.Fragment>
        ))}
      </dl>
    </section>
  );
};

export default CostDailyTrendCard;
