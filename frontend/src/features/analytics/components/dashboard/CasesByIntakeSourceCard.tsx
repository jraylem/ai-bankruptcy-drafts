import React from 'react';
import { FiInbox } from 'react-icons/fi';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  LabelList,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { useDashboardCases } from '../../hooks/useDashboardCases';
import { AnalyticsBodySkeleton } from '../AnalyticsSkeleton';
import { AnalyticsChartTooltip } from '../chartShared';
import { chartBarCursorStyle, chartTooltipWrapperStyle } from '../chartStyles';
import { SectionCard } from '../SectionCard';

export const CasesByIntakeSourceCard: React.FC = () => {
  const { data: cases, isLoading, isFetching } = useDashboardCases();
  const data = [
    { name: 'Manual', value: cases?.active_cases.manual ?? 0, fill: '#4f46e5' },
    { name: 'Summoned', value: cases?.active_cases.summoned ?? 0, fill: '#818cf8' },
    {
      name: 'Converted from Pending',
      value: cases?.active_cases.from_pending ?? 0,
      fill: '#7c3aed',
    },
  ];
  const hasData = data.some((item) => item.value > 0);
  const showSkeleton = !cases || isLoading || isFetching;

  return (
    <SectionCard
      title={
        <div className="flex items-center gap-2">
          <FiInbox className="h-4 w-4 text-app-accent" />
          <span>Cases by Intake Source</span>
        </div>
      }
    >
      {showSkeleton ? (
        <AnalyticsBodySkeleton className="h-64" />
      ) : hasData ? (
        <div className="h-64">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart
              data={data}
              margin={{ top: 8, right: 8, left: -16, bottom: 0 }}
              barCategoryGap={28}
            >
              <CartesianGrid stroke="var(--app-chart-grid)" vertical={false} />
              <XAxis
                dataKey="name"
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
              <Bar dataKey="value" name="Cases" radius={[10, 10, 0, 0]}>
                <LabelList
                  dataKey="value"
                  position="top"
                  fill="var(--app-chart-axis)"
                  fontSize={11}
                />
                {data.map((entry) => (
                  <Cell key={entry.name} fill={entry.fill} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      ) : (
        <div className="flex h-64 items-center justify-center rounded-2xl border border-dashed border-border bg-surface-muted/70 px-6 text-center text-sm text-muted">
          No intake source activity recorded for the selected period yet.
        </div>
      )}
    </SectionCard>
  );
};
