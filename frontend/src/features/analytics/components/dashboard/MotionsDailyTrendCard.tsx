import React, { useMemo, useState } from 'react';
import { FiActivity } from 'react-icons/fi';
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { useDashboardMotionsDaily } from '../../hooks/useDashboardMotionsDaily';
import { AnalyticsBodySkeleton, InlineValueSkeleton } from '../AnalyticsSkeleton';
import { AnalyticsMetricDropdown } from '../AnalyticsMetricDropdown';
import { AnalyticsChartTooltip } from '../chartShared';
import { chartBarCursorStyle, chartTooltipWrapperStyle } from '../chartStyles';
import { SectionCard } from '../SectionCard';
import { formatCompactNumber } from '../../utils/dashboard.mappers';
import { MOTION_STATUS_COLORS } from '../../utils/statusVisuals';

const MOTION_METRICS = [
  { key: 'completed', label: 'Completed', color: MOTION_STATUS_COLORS.completed },
  { key: 'pending', label: 'Pending', color: MOTION_STATUS_COLORS.pending },
  { key: 'failed', label: 'Failed', color: MOTION_STATUS_COLORS.failed },
  { key: 'cancelled', label: 'Cancelled', color: MOTION_STATUS_COLORS.cancelled },
] as const;

export const MotionsDailyTrendCard: React.FC = () => {
  const { data, isLoading, isFetching } = useDashboardMotionsDaily();
  const [selectedMetrics, setSelectedMetrics] = useState<Array<(typeof MOTION_METRICS)[number]['key']>>(
    MOTION_METRICS.map((metric) => metric.key),
  );
  const chartData = useMemo(
    () =>
      (data?.data ?? []).map((item) => ({
        day: new Date(item.date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
        completed: Number.isFinite(item.completed) ? item.completed : 0,
        pending: Number.isFinite(item.pending) ? item.pending : 0,
        failed: Number.isFinite(item.failed) ? item.failed : 0,
        cancelled: Number.isFinite(item.cancelled) ? item.cancelled : 0,
      })),
    [data],
  );
  const totalDrafts = chartData.reduce(
    (sum, item) => sum + selectedMetrics.reduce((metricSum, metric) => metricSum + item[metric], 0),
    0,
  );
  const peakDrafts = Math.max(
    ...chartData.map((item) => selectedMetrics.reduce((metricSum, metric) => metricSum + item[metric], 0)),
    0,
  );
  const latestDrafts =
    chartData.length > 0
      ? selectedMetrics.reduce((metricSum, metric) => metricSum + (chartData.at(-1)?.[metric] ?? 0), 0)
      : 0;
  const hasData = chartData.some((item) => selectedMetrics.some((metric) => item[metric] > 0));
  const showSkeleton = !data || isLoading || isFetching;

  return (
    <SectionCard
      headerClassName="items-start"
      title={
        <div>
          <div className="flex items-center gap-2">
            <FiActivity className="h-4 w-4 text-app-accent" />
            <span>Motions Drafted Daily</span>
          </div>
          <p className="mt-1 text-xs font-normal text-subtle">
            Daily drafted motions by selected status.
          </p>
        </div>
      }
      action={
        <AnalyticsMetricDropdown
          label="Statuses"
          options={[
            { label: 'All', value: '__all__', color: 'var(--app-chart-axis)' },
            ...MOTION_METRICS.map((metric) => ({
              label: metric.label,
              value: metric.key,
              color: metric.color,
            })),
          ]}
          selectedValues={selectedMetrics}
          onChange={(values) =>
            setSelectedMetrics(values as Array<(typeof MOTION_METRICS)[number]['key']>)
          }
        />
      }
    >
      <div className="mb-4 grid grid-cols-3 gap-3">
        <div className="rounded-2xl bg-app-accent-soft px-4 py-2.5">
          <p className="text-[10px] font-bold uppercase tracking-[0.18em] text-app-accent-text">
            Total in Range
          </p>
          {showSkeleton ? (
            <InlineValueSkeleton className="mt-1.5 h-8 w-16" />
          ) : (
            <p className="mt-1.5 font-poppins text-[28px] font-bold leading-none text-app-accent-text">
              {formatCompactNumber(totalDrafts)}
            </p>
          )}
        </div>
        <div className="rounded-2xl bg-surface-muted/70 px-4 py-2.5">
          <p className="text-[10px] font-bold uppercase tracking-[0.18em] text-subtle">
            Peak Day Total
          </p>
          {showSkeleton ? (
            <InlineValueSkeleton className="mt-1.5 h-8 w-16" />
          ) : (
            <p className="mt-1.5 font-poppins text-[28px] font-bold leading-none text-text">
              {formatCompactNumber(peakDrafts)}
            </p>
          )}
        </div>
        <div className="rounded-2xl bg-app-accent-soft px-4 py-2.5">
          <p className="text-[10px] font-bold uppercase tracking-[0.18em] text-indigo-400">
            Most Recent Day Total
          </p>
          {showSkeleton ? (
            <InlineValueSkeleton className="mt-1.5 h-8 w-16" />
          ) : (
            <p className="mt-1.5 font-poppins text-[28px] font-bold leading-none text-app-accent-text">
              {formatCompactNumber(latestDrafts)}
            </p>
          )}
        </div>
      </div>

      {showSkeleton ? (
        <AnalyticsBodySkeleton className="h-44" />
      ) : hasData ? (
        <div className="h-44">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={chartData} margin={{ top: 8, right: 12, left: -20, bottom: 0 }}>
              <CartesianGrid stroke="var(--app-chart-grid)" vertical={false} strokeDasharray="4 4" />
              <XAxis dataKey="day" axisLine={false} tickLine={false} tick={{ fill: 'var(--app-chart-axis)', fontSize: 11 }} />
              <YAxis axisLine={false} tickLine={false} tick={{ fill: 'var(--app-chart-axis)', fontSize: 11 }} />
              <Tooltip
                content={<AnalyticsChartTooltip />}
                wrapperStyle={chartTooltipWrapperStyle}
                cursor={chartBarCursorStyle}
              />
              {MOTION_METRICS.filter((metric) => selectedMetrics.includes(metric.key)).map((metric) => (
                <Bar
                  key={metric.key}
                  dataKey={metric.key}
                  name={metric.label}
                  stackId="motions"
                  fill={metric.color}
                  radius={[selectedMetrics.length === 1 ? 6 : 0, selectedMetrics.length === 1 ? 6 : 0, 0, 0]}
                  maxBarSize={26}
                />
              ))}
            </BarChart>
          </ResponsiveContainer>
        </div>
      ) : (
        <div className="flex h-44 flex-col items-center justify-center rounded-2xl bg-surface-muted/70 text-center">
          <p className="text-sm font-semibold text-text-secondary">No motion activity in this period yet</p>
          <p className="mt-2 max-w-xs text-xs text-subtle">
            Daily motion counts for the selected statuses will appear once records are available.
          </p>
        </div>
      )}
    </SectionCard>
  );
};
