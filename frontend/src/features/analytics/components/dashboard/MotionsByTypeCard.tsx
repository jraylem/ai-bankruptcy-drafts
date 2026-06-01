import React, { useState } from 'react';
import { FiLayers } from 'react-icons/fi';
import { Cell, Pie, PieChart, ResponsiveContainer, Sector, Tooltip } from 'recharts';
import { useDashboardMotionsByType } from '../../hooks/useDashboardMotionsByType';
import type { DashboardMotionsByTypePoint } from '../../types/dashboard.types';
import {
  AnalyticsBodySkeleton,
  InlineValueSkeleton,
  SkeletonBlock,
} from '../AnalyticsSkeleton';
import { chartTooltipWrapperStyle } from '../chartStyles';
import { SectionCard } from '../SectionCard';
import { formatAnalyticsNumber } from '../../utils/dashboard.mappers';

const typeColors = ['#4f46e5', '#7c3aed', '#8b5cf6', '#a78bfa', '#c4b5fd'];

const normalizeMotionTypeLabel = (label: string) => {
  const dehyphenated = label.replace(/-/g, ' ').replace(/\s+/g, ' ').trim();
  if (!dehyphenated) {
    return label;
  }

  if (dehyphenated === dehyphenated.toLowerCase()) {
    return dehyphenated.replace(/\b\w/g, (char) => char.toUpperCase());
  }

  return dehyphenated;
};

type PieSectorProps = React.ComponentProps<typeof Sector> & {
  index?: number;
};

type MotionTypeDatum = {
  label: string;
  count: number;
  motionType: string;
  completed: number;
  pending: number;
  failed: number;
  cancelled: number;
};

type MotionTypeTooltipProps = {
  active?: boolean;
  payload?: Array<{
    payload?: MotionTypeDatum;
  }>;
};

const getStatusSummary = (item: MotionTypeDatum) => {
  if (item.completed === item.count && item.count > 0) {
    return { label: 'Completed', value: '100%', tone: 'emerald' as const };
  }

  if (item.pending > 0) {
    return {
      label: 'Pending',
      value: formatAnalyticsNumber(item.pending, { maximumFractionDigits: 0 }),
      tone: 'amber' as const,
    };
  }

  if (item.failed > 0) {
    return {
      label: 'Failed',
      value: formatAnalyticsNumber(item.failed, { maximumFractionDigits: 0 }),
      tone: 'rose' as const,
    };
  }

  if (item.cancelled > 0) {
    return {
      label: 'Cancelled',
      value: formatAnalyticsNumber(item.cancelled, { maximumFractionDigits: 0 }),
      tone: 'slate' as const,
    };
  }

  return {
    label: 'Completed',
    value: formatAnalyticsNumber(item.completed, { maximumFractionDigits: 0 }),
    tone: 'emerald' as const,
  };
};

const toneTextClasses = {
  amber: 'text-app-warning-text',
  emerald: 'text-app-success-text',
  rose: 'text-app-danger-text',
  slate: 'text-text-secondary',
};

const MotionTypeTooltip: React.FC<MotionTypeTooltipProps> = ({ active, payload }) => {
  const item = payload?.[0]?.payload;

  if (!active || !item) return null;

  const rows = [
    { label: 'Total', value: item.count },
    { label: 'Completed', value: item.completed },
    { label: 'Pending', value: item.pending },
    { label: 'Failed', value: item.failed },
    { label: 'Cancelled', value: item.cancelled },
  ].filter((row) => row.label === 'Total' || row.value > 0);

  return (
    <div className="min-w-[160px] rounded-xl border border-border/70 bg-surface-muted px-3 py-2.5 shadow-[0_18px_42px_rgba(15,23,42,0.14)] backdrop-blur-sm">
      <p className="text-[11px] font-semibold leading-4 text-text">{item.label}</p>
      <div className="mt-1.5 space-y-1">
        {rows.map((row) => (
          <div
            key={row.label}
            className="flex items-center justify-between gap-3 text-[10px] leading-4"
          >
            <span className="font-medium text-muted">{row.label}</span>
            <span className="font-semibold text-app-accent-text">
              {formatAnalyticsNumber(row.value, { maximumFractionDigits: 0 })}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
};

const renderTypeShape = (props: PieSectorProps, isActive: boolean) => {
  const outerRadius = typeof props.outerRadius === 'number' ? props.outerRadius : 92;

  if (!isActive) {
    return <Sector {...props} />;
  }

  return (
    <g>
      <Sector {...props} outerRadius={outerRadius + 6} />
      <Sector
        {...props}
        outerRadius={outerRadius + 10}
        innerRadius={outerRadius + 7}
        fill={props.fill}
        opacity={0.22}
      />
    </g>
  );
};

export const MotionsByTypeCard: React.FC = () => {
  const { data, isLoading, isFetching } = useDashboardMotionsByType();
  const [activeSliceIndex, setActiveSliceIndex] = useState<number | undefined>(undefined);
  const [activeLegendIndex, setActiveLegendIndex] = useState<number | undefined>(undefined);
  const typeData =
    data?.data
      .map((item: DashboardMotionsByTypePoint) => ({
        label: normalizeMotionTypeLabel(item.display_name),
        count: item.total,
        motionType: item.motion_type,
        completed: item.completed,
        pending: item.pending,
        failed: item.failed,
        cancelled: item.cancelled,
      }))
      .sort((a, b) => b.count - a.count) ?? [];
  const total = typeData.reduce((sum, item) => sum + item.count, 0);
  const topTypes = typeData.slice(0, 4);
  const showSkeleton = !data || isLoading || isFetching;
  const hasData = typeData.length > 0 && total > 0;
  const activeIndex = activeLegendIndex ?? activeSliceIndex;
  return (
    <SectionCard
      className="h-full"
      title={
        <div className="flex items-center gap-2">
          <FiLayers className="h-4 w-4 text-app-accent" />
          <span>Motions by Type</span>
        </div>
      }
    >
      {showSkeleton ? (
        <div className="flex h-full flex-1 flex-col gap-3">
          <div className="mx-auto">
            <AnalyticsBodySkeleton className="h-[208px] w-[228px] rounded-full" />
          </div>

          <div className="grid gap-2.5 min-[480px]:grid-cols-2">
            {Array.from({ length: 4 }).map((_, index) => (
              <div key={index} className="rounded-2xl bg-surface-muted/70 px-3 py-2">
                <div className="flex items-start justify-between gap-2">
                  <div className="flex min-w-0 items-start gap-3">
                    <span className="mt-1 h-3 w-3 shrink-0 rounded-full bg-border/80" />
                    <SkeletonBlock className="h-4 w-full max-w-[140px]" />
                  </div>
                  <InlineValueSkeleton className="h-8 w-8 shrink-0" />
                </div>
                <InlineValueSkeleton className="mt-1.5 h-3 w-16" />
              </div>
            ))}
          </div>
        </div>
      ) : hasData ? (
        <div className="flex h-full flex-1 flex-col gap-3">
          <div className="analytics-chart-shell relative mx-auto h-[208px] w-full max-w-[228px]">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={typeData}
                  dataKey="count"
                  nameKey="label"
                  innerRadius={62}
                  outerRadius={92}
                  onMouseEnter={(_, index) => setActiveSliceIndex(index)}
                  onMouseLeave={() => setActiveSliceIndex(undefined)}
                  shape={(props) =>
                    renderTypeShape(
                      props as PieSectorProps,
                      (props as PieSectorProps).index === activeIndex
                    )
                  }
                  paddingAngle={3}
                  stroke="none"
                >
                  {typeData.map((entry, index) => (
                    <Cell key={entry.motionType} fill={typeColors[index % typeColors.length]} />
                  ))}
                </Pie>
                <Tooltip content={<MotionTypeTooltip />} wrapperStyle={chartTooltipWrapperStyle} />
              </PieChart>
            </ResponsiveContainer>
            <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
              <span className="text-[10px] font-bold uppercase tracking-[0.18em] text-subtle">
                Drafted
              </span>
              <span className="mt-1 font-poppins text-3xl font-bold text-text">
                {formatAnalyticsNumber(total, { maximumFractionDigits: 0 })}
              </span>
            </div>
          </div>

          <div className="grid gap-2.5 min-[480px]:grid-cols-2">
            {topTypes.map((item, index) => {
              const statusSummary = getStatusSummary(item);

              return (
                <div
                  key={item.motionType}
                  title={item.label}
                  className={`cursor-pointer rounded-2xl px-3 py-2.5 transition-colors ${
                    activeIndex === index ? 'bg-app-accent-soft shadow-sm' : 'bg-surface-muted/70'
                  }`}
                  onMouseEnter={() => setActiveLegendIndex(index)}
                  onMouseLeave={() => setActiveLegendIndex(undefined)}
                >
                  <p className="break-words text-[13px] font-semibold leading-5 text-text-secondary">
                    {item.label}
                  </p>
                  <div className="mt-1 flex items-center gap-2">
                    <span
                      className="h-3 w-3 shrink-0 rounded-full"
                      style={{ backgroundColor: typeColors[index % typeColors.length] }}
                    />
                    <span className="font-poppins text-[18px] font-bold leading-none text-text md:text-[20px]">
                      {formatAnalyticsNumber(item.count, { maximumFractionDigits: 0 })}
                    </span>
                  </div>
                  <p
                    className={`mt-1 text-[11px] leading-4 ${toneTextClasses[statusSummary.tone]}`}
                  >
                    {statusSummary.label}: {statusSummary.value}
                  </p>
                </div>
              );
            })}
          </div>
        </div>
      ) : (
        <div className="flex h-full flex-1 flex-col items-center justify-center rounded-2xl bg-surface-muted/70 text-center">
          <p className="text-sm font-semibold text-text-secondary">
            No motion type activity in this period yet
          </p>
          <p className="mt-2 max-w-xs text-xs text-subtle">
            Motion type distribution will appear here once drafted motions are recorded for the
            selected period.
          </p>
        </div>
      )}
    </SectionCard>
  );
};
