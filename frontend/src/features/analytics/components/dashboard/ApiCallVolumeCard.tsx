import React from 'react';
import { FiServer } from 'react-icons/fi';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { AnalyticsBodySkeleton, InlineValueSkeleton } from '../AnalyticsSkeleton';
import { AnalyticsChartTooltip } from '../chartShared';
import { chartBarCursorStyle, chartTooltipWrapperStyle } from '../chartStyles';
import { SectionCard } from '../SectionCard';
import { useDashboardApiCalls } from '../../hooks/useDashboardApiCalls';
import { formatAnalyticsNumber, formatCompactNumber } from '../../utils/dashboard.mappers';
import { STATUS_COLOR } from '../../utils/statusVisuals';

export const ApiCallVolumeCard: React.FC = () => {
  const { data: apiCalls, isLoading, isFetching } = useDashboardApiCalls();
  const totalCalls = apiCalls?.total ?? 0;
  const errorCalls = apiCalls?.error_total ?? 0;
  const successCalls = Math.max(totalCalls - errorCalls, 0);
  const successRate = totalCalls > 0 ? (successCalls / totalCalls) * 100 : 0;
  const successRateLabel = `${formatAnalyticsNumber(successRate, {
    minimumFractionDigits: successRate > 0 && successRate < 100 ? 1 : 0,
    maximumFractionDigits: 1,
  })}%`;
  const chartData =
    apiCalls?.daily.map((item) => ({
      day: new Date(item.date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
      success: Math.max(item.count - item.error_count, 0),
      error: item.error_count,
    })) ?? [];
  const showSkeleton = !apiCalls || isLoading || isFetching;

  return (
    <SectionCard
      className="h-full"
      headerClassName="items-start"
      title={
        <div>
          <div className="flex items-center gap-2">
            <FiServer className="h-4 w-4 text-app-accent" />
            <span>API Call Volume</span>
          </div>
          <p className="mt-1 text-xs font-normal text-subtle">
            Daily successful and failed API calls.
          </p>
        </div>
      }
    >
      <div className="flex h-full flex-1 flex-col gap-4">
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          <div className="rounded-2xl bg-surface-muted/70 px-3 py-2.5">
            <p className="text-[10px] font-bold uppercase tracking-[0.14em] text-subtle">
              Total
            </p>
            {showSkeleton ? (
              <InlineValueSkeleton className="mt-1 h-7 w-14" />
            ) : (
              <p className="mt-1 font-poppins text-xl font-bold text-text">
                {formatCompactNumber(totalCalls)}
              </p>
            )}
          </div>
          <div className="rounded-2xl bg-app-accent-soft px-3 py-2.5">
            <p className="text-[10px] font-bold uppercase tracking-[0.14em] text-indigo-400">
              Success
            </p>
            {showSkeleton ? (
              <InlineValueSkeleton className="mt-1 h-7 w-14" />
            ) : (
              <p className="mt-1 font-poppins text-xl font-bold text-app-accent-text">
                {formatCompactNumber(successCalls)}
              </p>
            )}
          </div>
          <div className="rounded-2xl bg-app-danger-soft px-3 py-2.5">
            <p className="text-[10px] font-bold uppercase tracking-[0.14em] text-app-danger-text">
              Errors
            </p>
            {showSkeleton ? (
              <InlineValueSkeleton className="mt-1 h-7 w-14" />
            ) : (
              <p className="mt-1 font-poppins text-xl font-bold text-app-danger-text">
                {formatCompactNumber(errorCalls)}
              </p>
            )}
          </div>
          <div className="rounded-2xl bg-app-success-soft px-3 py-2.5">
            <p className="text-[10px] font-bold uppercase tracking-[0.14em] text-app-success-text">
              Success Rate
            </p>
            {showSkeleton ? (
              <InlineValueSkeleton className="mt-1 h-7 w-14" />
            ) : (
              <p className="mt-1 font-poppins text-xl font-bold text-app-success-text">
                {successRateLabel}
              </p>
            )}
          </div>
        </div>

        {showSkeleton ? (
          <AnalyticsBodySkeleton className="h-[220px]" />
        ) : chartData.length > 0 ? (
          <div className="h-[220px]">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={chartData} margin={{ top: 8, right: 8, left: -12, bottom: 0 }}>
                <CartesianGrid stroke="var(--app-chart-grid)" vertical={false} />
                <XAxis
                  dataKey="day"
                  axisLine={false}
                  tickLine={false}
                  tick={{ fill: 'var(--app-chart-axis)', fontSize: 11 }}
                />
                <YAxis axisLine={false} tickLine={false} tick={{ fill: 'var(--app-chart-axis)', fontSize: 11 }} />
                <Tooltip
                  content={<AnalyticsChartTooltip />}
                  wrapperStyle={chartTooltipWrapperStyle}
                  cursor={chartBarCursorStyle}
                />
                <Legend
                  iconType="circle"
                  wrapperStyle={{ fontSize: '11px', color: 'var(--app-chart-axis)' }}
                />
                <Bar
                  dataKey="success"
                  name="Success"
                  fill={STATUS_COLOR.success}
                  radius={[6, 6, 0, 0]}
                />
                <Bar dataKey="error" name="Errors" fill={STATUS_COLOR.danger} radius={[6, 6, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        ) : (
          <div className="flex h-[220px] items-center justify-center rounded-2xl border border-dashed border-border bg-surface-muted/70 px-6 text-center text-sm text-muted">
            No API call activity recorded for the selected period yet.
          </div>
        )}
      </div>
    </SectionCard>
  );
};
