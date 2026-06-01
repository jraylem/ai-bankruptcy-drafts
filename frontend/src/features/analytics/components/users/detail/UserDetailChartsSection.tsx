import React from 'react';
import { FiBarChart2, FiTrendingUp } from 'react-icons/fi';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { SectionCard } from '@/features/analytics/components/SectionCard';
import { AnalyticsChartTooltip } from '@/features/analytics/components/chartShared';
import {
  chartBarCursorStyle,
  chartLineCursorStyle,
  chartTooltipWrapperStyle,
} from '@/features/analytics/components/chartStyles';
import { useUserDetailPageContext } from './UserDetailPageContext';

export const UserDetailChartsSection: React.FC = () => {
  const { detail } = useUserDetailPageContext();

  return (
    <section className="mb-6 grid gap-6 xl:grid-cols-2">
      <SectionCard
        title={
          <div className="flex items-center gap-2">
            <FiTrendingUp className="h-4 w-4 text-app-accent" />
            <span>30-Day Activity Trend</span>
          </div>
        }
        action={
          <div className="flex items-center gap-3 text-[11px] text-muted">
            <span className="inline-flex items-center gap-1.5 whitespace-nowrap">
              <span className="h-2 w-2 rounded-full bg-app-accent" />
              Motions Completed
            </span>
            <span className="inline-flex items-center gap-1.5 whitespace-nowrap">
              <span className="h-2 w-2 rounded-full bg-app-success-text" />
              Active Minutes
            </span>
          </div>
        }
      >
        <div className="h-60">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={detail.trend_30d} margin={{ top: 8, right: 8, left: -20, bottom: 0 }}>
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
                cursor={chartLineCursorStyle}
              />
              <Line
                type="monotone"
                dataKey="motions"
                name="Motions completed"
                stroke="var(--app-accent)"
                strokeWidth={2.5}
                dot={false}
                activeDot={{
                  r: 5,
                  stroke: 'var(--app-bg-surface)',
                  strokeWidth: 2,
                  fill: 'var(--app-accent)',
                }}
              />
              <Line
                type="monotone"
                dataKey="activeMinutes"
                name="Active minutes"
                stroke="var(--app-success-text)"
                strokeWidth={2.25}
                dot={false}
                activeDot={{
                  r: 5,
                  stroke: 'var(--app-bg-surface)',
                  strokeWidth: 2,
                  fill: 'var(--app-success-text)',
                }}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </SectionCard>

      <SectionCard
        title={
          <div className="flex items-center gap-2">
            <FiBarChart2 className="h-4 w-4 text-app-accent" />
            <span>Top Motion Types</span>
          </div>
        }
        action={
          <div className="flex items-center gap-3 text-[11px] text-muted">
            <span className="inline-flex items-center gap-1.5 whitespace-nowrap">
              <span className="h-2 w-2 rounded-full bg-app-accent" />
              Drafted
            </span>
            <span className="inline-flex items-center gap-1.5 whitespace-nowrap">
              <span className="h-2 w-2 rounded-full bg-app-success-text" />
              Completed
            </span>
          </div>
        }
      >
        <div className="h-60">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart
              data={detail.top_motion_types}
              margin={{ top: 8, right: 8, left: 0, bottom: 8 }}
            >
              <CartesianGrid stroke="var(--app-chart-grid)" vertical={false} />
              <XAxis
                dataKey="motion_type"
                axisLine={false}
                tickLine={false}
                tick={{ fill: 'var(--app-chart-axis)', fontSize: 10 }}
                interval={0}
                angle={-22}
                textAnchor="end"
                height={62}
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
              <Bar
                dataKey="drafted"
                name="Drafted"
                fill="var(--app-accent)"
                radius={[6, 6, 0, 0]}
              />
              <Bar
                dataKey="completed"
                name="Completed"
                fill="var(--app-success-text)"
                radius={[6, 6, 0, 0]}
              />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </SectionCard>
    </section>
  );
};
