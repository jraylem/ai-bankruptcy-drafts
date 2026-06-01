import React from 'react';
import { Link } from 'react-router-dom';
import { FiUsers } from 'react-icons/fi';
import { Bar, BarChart, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';

import { AnalyticsBodySkeleton, InlineValueSkeleton } from '../AnalyticsSkeleton';
import { AnalyticsChartTooltip } from '../chartShared';
import { chartBarCursorStyle, chartTooltipWrapperStyle } from '../chartStyles';

import { SectionCard } from '../SectionCard';
import { useDashboardUsers } from '../../hooks/useDashboardUsers';
import { formatCompactNumber } from '../../utils/dashboard.mappers';

export const UsersOverviewCard: React.FC = () => {
  const { data: users, isLoading, isFetching } = useDashboardUsers();
  const total = users?.total ?? 0;
  const activeInRange = users?.active_in_range ?? 0;
  const newInRange = users?.new_in_range ?? 0;
  const activeRate = total > 0 ? Math.round((activeInRange / total) * 100) : 0;
  const chartData = [
    { name: 'Total', value: total, fill: '#eef2ff' },
    { name: 'New', value: newInRange, fill: '#a5b4fc' },
    { name: 'Active', value: activeInRange, fill: '#4f46e5' },
  ];
  const hasData = chartData.some((item) => item.value > 0);

  const showSkeleton = !users || isLoading || isFetching;

  return (
    <SectionCard
      className="h-full"
      title={
        <div className="flex items-center gap-2">
          <FiUsers className="h-4 w-4 text-app-accent" />
          <span>Users Overview</span>
        </div>
      }
      action={
        <Link
          to="/analytics/users"
          className="inline-flex items-center rounded-lg border border-border px-2.5 py-1 text-xs font-medium text-app-accent-text transition hover:bg-app-accent-soft"
        >
          View all
        </Link>
      }
    >
      <div className="flex h-full min-h-[240px] flex-col">
        <div className="mb-4">
          <div className="mt-2 flex items-baseline gap-2">
            {showSkeleton ? (
              <>
                <InlineValueSkeleton className="h-9 w-12" />
                <InlineValueSkeleton className="h-5 w-14 rounded-full" />
              </>
            ) : (
              <>
                <span className="text-3xl font-bold text-text">
                  {formatCompactNumber(activeInRange)}
                </span>
                <span className="inline-flex items-center text-xs font-semibold text-app-success-text">
                  {activeRate}% active
                </span>
              </>
            )}
          </div>
        </div>

        {showSkeleton ? (
          <AnalyticsBodySkeleton className="h-[150px]" />
        ) : hasData ? (
          <div className="h-[150px]">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart
                data={chartData}
                margin={{ top: 8, right: 4, left: 4, bottom: 0 }}
                barCategoryGap={12}
              >
                <XAxis
                  dataKey="name"
                  axisLine={false}
                  tickLine={false}
                  tick={{ fill: 'var(--app-chart-axis)', fontSize: 11 }}
                />
                <YAxis hide />
                <Tooltip
                  content={<AnalyticsChartTooltip />}
                  wrapperStyle={chartTooltipWrapperStyle}
                  cursor={chartBarCursorStyle}
                />
                <Bar dataKey="value" name="Users" radius={[6, 6, 0, 0]} barSize={42}>
                  {chartData.map((entry) => (
                    <Cell key={entry.name} fill={entry.fill} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        ) : (
          <div className="flex h-[150px] items-center justify-center rounded-2xl border border-dashed border-border bg-surface-muted/70 px-6 text-center text-sm text-muted">
            No user activity recorded for the selected period yet.
          </div>
        )}

        <p className="mt-3 text-center text-xs text-subtle">
          Total, new, and active users in the selected period
        </p>
      </div>
    </SectionCard>
  );
};
