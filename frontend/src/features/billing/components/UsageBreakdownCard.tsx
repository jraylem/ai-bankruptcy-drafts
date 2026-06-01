import React from 'react';
import { FiMinus, FiTrendingDown, FiTrendingUp } from 'react-icons/fi';
import type { BillingUsageCategory } from '../types/billing.types';
import { BillingCard } from './BillingCard';

type Trend = 'down' | 'stable' | 'up';

const getTrend = (trendPct: number): { trend: Trend; trendLabel: string } => {
  if (trendPct > 0) {
    return { trend: 'up', trendLabel: `+${trendPct}%` };
  }

  if (trendPct < 0) {
    return { trend: 'down', trendLabel: `${trendPct}%` };
  }

  return { trend: 'stable', trendLabel: '0%' };
};

const TrendIndicator = ({ trend, trendLabel }: { trend: Trend; trendLabel: string }) => {
  if (trend === 'stable') {
    return (
      <span className="inline-flex items-center justify-end gap-1 text-xs font-medium text-muted">
        <FiMinus className="h-3.5 w-3.5" />
        {trendLabel}
      </span>
    );
  }

  const Icon = trend === 'up' ? FiTrendingUp : FiTrendingDown;
  const className = trend === 'up' ? 'text-app-warning-text' : 'text-app-success-text';

  return (
    <span
      className={`inline-flex items-center justify-end gap-1 text-xs font-semibold ${className}`}
    >
      <Icon className="h-3.5 w-3.5" />
      {trendLabel}
    </span>
  );
};

interface UsageBreakdownCardProps {
  isLoading: boolean;
  summaryLabel: string;
  usageCategories: BillingUsageCategory[];
}

export const UsageBreakdownCard: React.FC<UsageBreakdownCardProps> = ({
  isLoading,
  summaryLabel,
  usageCategories,
}) => (
  <BillingCard>
    <div className="px-5 pb-2 pt-5">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h2 className="font-poppins text-lg font-semibold text-text-secondary">
            Usage breakdown
          </h2>
          <p className="mt-1 text-sm text-muted">Current billing cycle usage by cost category.</p>
        </div>
      </div>
    </div>

    <div className="px-5 pb-5">
      <div className="overflow-x-auto rounded-2xl border border-border/70">
        <table className="min-w-full table-fixed border-collapse">
          <thead className="bg-surface-muted/75">
            <tr>
              <th className="w-[34%] px-4 py-3 text-left whitespace-nowrap">
                <span className="inline-flex items-center whitespace-nowrap text-[11px] font-semibold uppercase tracking-[0.12em] text-muted">
                  Category
                </span>
              </th>
              <th className="w-[16%] px-4 py-3 text-right whitespace-nowrap">
                <span className="inline-flex items-center whitespace-nowrap text-[11px] font-semibold uppercase tracking-[0.12em] text-muted">
                  Units used
                </span>
              </th>
              <th className="w-[16%] px-4 py-3 text-right whitespace-nowrap">
                <span className="inline-flex items-center whitespace-nowrap text-[11px] font-semibold uppercase tracking-[0.12em] text-muted">
                  Rate
                </span>
              </th>
              <th className="w-[18%] px-4 py-3 text-right whitespace-nowrap">
                <span className="inline-flex items-center whitespace-nowrap text-[11px] font-semibold uppercase tracking-[0.12em] text-muted">
                  Current charge
                </span>
              </th>
              <th className="w-[16%] px-4 py-3 text-right whitespace-nowrap">
                <span className="inline-flex items-center whitespace-nowrap text-[11px] font-semibold uppercase tracking-[0.12em] text-muted">
                  Trend
                </span>
              </th>
            </tr>
          </thead>
          <tbody>
            {isLoading
              ? Array.from({ length: 4 }).map((_, index) => (
                  <tr key={index} className="border-t border-border/70">
                    <td className="px-4 py-3" colSpan={5}>
                      <div className="h-9 animate-pulse rounded-lg bg-surface-muted" />
                    </td>
                  </tr>
                ))
              : usageCategories.map((category) => {
                  const trend = getTrend(category.trendPct);

                  return (
                    <tr
                      key={category.id}
                      className="border-t border-border/70 transition-colors hover:bg-activity-row-hover"
                    >
                      <td className="px-4 py-3">
                        <div className="flex min-w-0 items-start gap-3">
                          <span className="mt-0.5 grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-app-accent-soft text-app-accent-text">
                            <category.icon className="h-4 w-4" />
                          </span>
                          <div className="min-w-0">
                            <h3 className="truncate text-sm font-semibold text-text-secondary">
                              {category.label}
                            </h3>
                            <p className="mt-1 text-xs text-muted">{category.description}</p>
                          </div>
                        </div>
                      </td>
                      <td className="px-4 py-3 text-right font-mono text-sm text-text-secondary">
                        {category.usageLabel}
                      </td>
                      <td className="px-4 py-3 text-right text-sm text-muted">
                        {category.rateLabel}
                      </td>
                      <td className="px-4 py-3 text-right text-sm font-semibold text-text">
                        {category.chargeLabel}
                      </td>
                      <td className="px-4 py-3 text-right">
                        <TrendIndicator trend={trend.trend} trendLabel={trend.trendLabel} />
                      </td>
                    </tr>
                  );
                })}
            <tr className="border-t border-border/70 bg-surface-muted/60">
              <td className="px-4 py-3 text-sm font-semibold text-text" colSpan={3}>
                Total month-to-date
              </td>
              <td className="px-4 py-3 text-right text-sm font-semibold text-text">
                {summaryLabel}
              </td>
              <td className="px-4 py-3" />
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </BillingCard>
);
