import React, { lazy, Suspense } from 'react';
import { useQuery } from '@tanstack/react-query';

import { fetchCostsSummary } from '@/services/costs.service';

import { CostByKindCard } from './CostByKindCard';
import { CostCenterEmptyState } from './CostCenterEmptyState';
import { CostCenterErrorState } from './CostCenterErrorState';
import { CostCenterLayout } from './CostCenterLayout';
import { CostCenterSkeleton } from './CostCenterSkeleton';
import { CostCenterWorkflowRow } from './CostCenterWorkflowRow';
import { CostTotalsRow } from './CostTotalsRow';
import { useCostsSummary } from './useCostsSummary';

const CostDailyTrendCard = lazy(() => import('./CostDailyTrendCard'));

const TrendChartFallback: React.FC = () => (
  <div
    className="h-[260px] w-full rounded-lg border border-border bg-surface p-5"
    aria-hidden="true"
  >
    <div className="mb-4 h-4 w-24 animate-pulse rounded bg-surface-muted" />
    <div className="h-[200px] w-full animate-pulse rounded bg-surface-muted max-sm:h-[160px]" />
  </div>
);

export const CostCenterPage: React.FC = () => {
  const { data, range, setRange, isLoading, error, lastUpdatedAt, refetch } =
    useCostsSummary('month');

  // Side-quest weekly fetch — fires in parallel with the main query on
  // mount so the "This week" cell in the forecast strip doesn't wait
  // for the month query to resolve. Skipped when range==='week' since
  // the main query already covers that window.
  const weeklyQuery = useQuery({
    queryKey: ['costs-summary', 'week'],
    queryFn: async () => {
      const res = await fetchCostsSummary('week');
      if (!res.data) throw new Error(res.error ?? 'Failed to load weekly costs.');
      return res.data;
    },
    enabled: range !== 'week',
    staleTime: 30_000,
  });
  const weeklyTotal = weeklyQuery.data?.total_cost_usd ?? null;

  let body: React.ReactNode;
  if (error) {
    body = <CostCenterErrorState onRetry={refetch} />;
  } else if (isLoading && !data) {
    body = <CostCenterSkeleton />;
  } else if (!data) {
    body = null;
  } else {
    const hasAnySpend =
      (data.total_cost_usd ?? 0) > 0 || data.by_kind.length > 0;
    body = (
      <>
        <CostTotalsRow data={data} range={range} weeklyTotal={weeklyTotal} />
        <CostCenterWorkflowRow data={data} />
        {hasAnySpend ? (
          <section className="grid grid-cols-1 gap-4 lg:grid-cols-12">
            <div className="lg:col-span-7">
              <Suspense fallback={<TrendChartFallback />}>
                <CostDailyTrendCard series={data.daily_series} />
              </Suspense>
            </div>
            <div className="lg:col-span-5">
              <CostByKindCard
                byKind={data.by_kind}
                total={data.total_cost_usd}
              />
            </div>
          </section>
        ) : (
          <CostCenterEmptyState />
        )}
      </>
    );
  }

  return (
    <CostCenterLayout
      range={range}
      onRangeChange={setRange}
      lastUpdatedAt={lastUpdatedAt}
      isLoading={isLoading}
      onRefresh={refetch}
    >
      {body}
    </CostCenterLayout>
  );
};

export default CostCenterPage;
