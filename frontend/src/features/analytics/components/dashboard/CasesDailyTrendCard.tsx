import React, { useMemo, useState } from 'react';
import { FiTrendingUp } from 'react-icons/fi';
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { useDashboardCasesDaily } from '../../hooks/useDashboardCasesDaily';
import { AnalyticsBodySkeleton, InlineValueSkeleton } from '../AnalyticsSkeleton';
import { AnalyticsMetricDropdown } from '../AnalyticsMetricDropdown';
import { AnalyticsChartTooltip } from '../chartShared';
import { chartBarCursorStyle, chartTooltipWrapperStyle } from '../chartStyles';
import { SectionCard } from '../SectionCard';
import { formatCompactNumber } from '../../utils/dashboard.mappers';
import { CASE_STATUS_COLORS } from '../../utils/statusVisuals';

const CASE_METRICS = [
  { key: 'active', label: 'Active', color: CASE_STATUS_COLORS.active },
  { key: 'pending', label: 'Pending', color: CASE_STATUS_COLORS.pending },
  { key: 'inactive', label: 'Inactive', color: CASE_STATUS_COLORS.inactive },
] as const;

export const CasesDailyTrendCard: React.FC = () => {
  const { data, isLoading, isFetching } = useDashboardCasesDaily();
  const [selectedMetrics, setSelectedMetrics] = useState<
    Array<(typeof CASE_METRICS)[number]['key']>
  >(CASE_METRICS.map((metric) => metric.key));
  const chartData = useMemo(
    () =>
      (data?.data ?? []).map((item) => ({
        day: new Date(`${item.date}T00:00:00`).toLocaleDateString('en-US', {
          month: 'short',
          day: 'numeric',
        }),
        total: Number.isFinite(item.total) ? item.total : 0,
        active: Number.isFinite(item.active) ? item.active : 0,
        pending: Number.isFinite(item.pending) ? item.pending : 0,
        inactive: Number.isFinite(item.inactive) ? item.inactive : 0,
      })),
    [data]
  );
  const rangeActive = chartData.reduce((sum, item) => sum + item.active, 0);
  const rangePending = chartData.reduce((sum, item) => sum + item.pending, 0);
  const rangeInactive = chartData.reduce((sum, item) => sum + item.inactive, 0);
  const hasData = chartData.some((item) => selectedMetrics.some((metric) => item[metric] > 0));
  const showSkeleton = !data || isLoading || isFetching;

  return (
    <SectionCard
      headerClassName="items-start"
      title={
        <div>
          <div className="flex items-center gap-2">
            <FiTrendingUp className="h-4 w-4 text-app-accent" />
            <span>Case Intake by Day</span>
          </div>
          <p className="mt-1 text-xs font-normal text-subtle">
            Daily counts by selected case status.
          </p>
        </div>
      }
      action={
        <AnalyticsMetricDropdown
          label="Statuses"
          options={[
            { label: 'All', value: '__all__', color: 'var(--app-chart-axis)' },
            ...CASE_METRICS.map((metric) => ({
              label: metric.label,
              value: metric.key,
              color: metric.color,
            })),
          ]}
          selectedValues={selectedMetrics}
          onChange={(values) =>
            setSelectedMetrics(values as Array<(typeof CASE_METRICS)[number]['key']>)
          }
        />
      }
    >
      <div className="mb-4 grid grid-cols-3 gap-3">
        <div className="rounded-2xl bg-app-success-soft px-4 py-2.5">
          <p className="text-[10px] font-bold uppercase tracking-[0.18em] text-app-success-text">
            Active in Period
          </p>
          {showSkeleton ? (
            <InlineValueSkeleton className="mt-1.5 h-8 w-16" />
          ) : (
            <p className="mt-1.5 font-poppins text-[28px] font-bold leading-none text-app-success-text">
              {formatCompactNumber(rangeActive)}
            </p>
          )}
        </div>
        <div className="rounded-2xl bg-surface-muted/70 px-4 py-2.5">
          <p className="text-[10px] font-bold uppercase tracking-[0.18em] text-amber-500">
            Pending in Period
          </p>
          {showSkeleton ? (
            <InlineValueSkeleton className="mt-1.5 h-8 w-16" />
          ) : (
            <p className="mt-1.5 font-poppins text-[28px] font-bold leading-none text-text">
              {formatCompactNumber(rangePending)}
            </p>
          )}
        </div>
        <div className="rounded-2xl bg-surface-muted/70 px-4 py-2.5">
          <p className="text-[10px] font-bold uppercase tracking-[0.18em] text-subtle">
            Inactive in Period
          </p>
          {showSkeleton ? (
            <InlineValueSkeleton className="mt-1.5 h-8 w-16" />
          ) : (
            <p className="mt-1.5 font-poppins text-[28px] font-bold leading-none text-subtle">
              {formatCompactNumber(rangeInactive)}
            </p>
          )}
        </div>
      </div>

      {showSkeleton ? (
        <AnalyticsBodySkeleton className="h-44" />
      ) : hasData ? (
        <div className="h-44">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={chartData} margin={{ top: 8, right: 8, left: -20, bottom: 0 }}>
              <CartesianGrid stroke="var(--app-chart-grid)" vertical={false} />
              <XAxis
                dataKey="day"
                axisLine={false}
                tickLine={false}
                tick={{ fill: 'var(--app-chart-axis)', fontSize: 11 }}
              />
              <YAxis
                axisLine={false}
                tickLine={false}
                tick={{ fill: 'var(--app-chart-axis)', fontSize: 11 }}
              />
              <Tooltip
                content={<AnalyticsChartTooltip />}
                wrapperStyle={chartTooltipWrapperStyle}
                cursor={chartBarCursorStyle}
              />
              {CASE_METRICS.filter((metric) => selectedMetrics.includes(metric.key)).map(
                (metric) => (
                  <Bar
                    key={metric.key}
                    dataKey={metric.key}
                    name={metric.label}
                    fill={metric.color}
                    stackId="case-intake"
                    radius={[4, 4, 0, 0]}
                  />
                )
              )}
            </BarChart>
          </ResponsiveContainer>
        </div>
      ) : (
        <div className="flex h-44 flex-col items-center justify-center rounded-2xl bg-surface-muted/70 text-center">
          <p className="text-sm font-semibold text-text-secondary">No case activity in this period yet</p>
          <p className="mt-2 max-w-xs text-xs text-subtle">
            Daily case counts for the selected statuses will appear here once activity is recorded.
          </p>
        </div>
      )}
    </SectionCard>
  );
};
