import React from 'react';
import { FiMap } from 'react-icons/fi';
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
import { chartBarCursorStyle, chartTooltipWrapperStyle } from '../chartStyles';
import { SectionCard } from '../SectionCard';
import { formatDistrictLabel } from '../../utils/districtLabels';
import { formatAnalyticsNumber } from '../../utils/dashboard.mappers';

type DistrictTooltipProps = {
  active?: boolean;
  payload?: Array<{
    color?: string;
    value?: number;
    payload?: {
      code: string;
      fullName: string;
      value: number;
    };
  }>;
};

const DistrictTooltip: React.FC<DistrictTooltipProps> = ({ active, payload }) => {
  const item = payload?.[0]?.payload;
  if (!active || !item) return null;

  return (
    <div className="min-w-[180px] rounded-xl border border-border/70 bg-surface-muted/95 px-3 py-2.5 shadow-[0_18px_42px_rgba(15,23,42,0.14)] backdrop-blur-sm">
      <p className="text-[11px] font-semibold leading-4 text-text">
        {item.code} - {item.fullName}
      </p>
      <div className="mt-1.5 flex items-center gap-1.5 text-[10px] leading-4">
        <span className="h-2 w-2 rounded-full bg-app-accent" />
        <span className="font-medium text-muted">Active Cases</span>
        <span className="text-subtle">:</span>
        <span className="font-semibold text-app-accent-text">
          {formatAnalyticsNumber(item.value, { maximumFractionDigits: 0 })}
        </span>
      </div>
    </div>
  );
};

export const ActiveCasesByDistrictCard: React.FC = () => {
  const { data: cases, isLoading, isFetching } = useDashboardCases();
  const districts = cases?.by_district_active;
  const data = [
    {
      code: 'FLNB',
      fullName: formatDistrictLabel('flnb', { includeCode: false, fallback: 'Unknown' }),
      value: districts?.flnb ?? 0,
      fill: '#4f46e5',
    },
    {
      code: 'FLMB',
      fullName: formatDistrictLabel('flmb', { includeCode: false, fallback: 'Unknown' }),
      value: districts?.flmb ?? 0,
      fill: '#6366f1',
    },
    {
      code: 'FLSB',
      fullName: formatDistrictLabel('flsb', { includeCode: false, fallback: 'Unknown' }),
      value: districts?.flsb ?? 0,
      fill: '#818cf8',
    },
    {
      code: 'PAWB',
      fullName: formatDistrictLabel('pawb', { includeCode: false, fallback: 'Unknown' }),
      value: districts?.pawb ?? 0,
      fill: '#a5b4fc',
    },
    {
      code: 'OTHER',
      fullName: formatDistrictLabel('other', { includeCode: false, fallback: 'Other' }),
      value: districts?.other ?? 0,
      fill: '#c7d2fe',
    },
  ];
  const hasData = data.some((item) => item.value > 0);
  const showSkeleton = !cases || isLoading || isFetching;

  return (
    <SectionCard
      title={
        <div className="flex items-center gap-2">
          <FiMap className="h-4 w-4 text-app-accent" />
          <span>Cases by District</span>
        </div>
      }
    >
      {showSkeleton ? (
        <AnalyticsBodySkeleton className="h-56" />
      ) : hasData ? (
        <div className="h-56">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart
              data={data}
              layout="vertical"
              margin={{ top: 0, right: 8, left: 8, bottom: 0 }}
              barCategoryGap={14}
            >
              <CartesianGrid stroke="var(--app-chart-grid)" horizontal={false} />
              <XAxis
                axisLine={false}
                tickLine={false}
                tick={{ fill: 'var(--app-chart-axis)', fontSize: 11 }}
                type="number"
              />
              <YAxis
                dataKey="code"
                type="category"
                axisLine={false}
                tickLine={false}
                tick={{ fill: 'var(--app-chart-axis)', fontSize: 12, fontWeight: 600 }}
                width={58}
              />
              <Tooltip
                content={<DistrictTooltip />}
                wrapperStyle={chartTooltipWrapperStyle}
                cursor={chartBarCursorStyle}
              />
              <Bar dataKey="value" name="Active Cases" radius={[0, 10, 10, 0]} barSize={18}>
                <LabelList
                  dataKey="value"
                  position="right"
                  fill="var(--app-chart-axis)"
                  fontSize={11}
                />
                {data.map((entry) => (
                  <Cell key={entry.code} fill={entry.fill} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      ) : (
        <div className="flex h-56 items-center justify-center rounded-2xl border border-dashed border-border bg-surface-muted/70 px-6 text-center text-sm text-muted">
          No district activity recorded for the selected period yet.
        </div>
      )}
    </SectionCard>
  );
};
