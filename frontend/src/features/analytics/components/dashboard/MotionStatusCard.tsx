import React, { useState } from 'react';
import { FiCheckCircle } from 'react-icons/fi';
import { Cell, Pie, PieChart, ResponsiveContainer, Sector, Tooltip } from 'recharts';
import { useDashboardMotions } from '../../hooks/useDashboardMotions';
import { formatCompactNumber } from '../../utils/dashboard.mappers';
import { AnalyticsBodySkeleton, InlineValueSkeleton } from '../AnalyticsSkeleton';
import { AnalyticsChartTooltip } from '../chartShared';
import { chartTooltipWrapperStyle } from '../chartStyles';
import { SectionCard } from '../SectionCard';
import { MOTION_STATUS_COLORS } from '../../utils/statusVisuals';

type PieSectorProps = React.ComponentProps<typeof Sector> & {
  index?: number;
};

const renderStatusShape = (props: PieSectorProps, isActive: boolean) => {
  const outerRadius = typeof props.outerRadius === 'number' ? props.outerRadius : 88;

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

export const MotionStatusCard: React.FC = () => {
  const { data: motions, isLoading, isFetching } = useDashboardMotions();
  const [activeSliceIndex, setActiveSliceIndex] = useState<number | undefined>(undefined);
  const [activeLegendIndex, setActiveLegendIndex] = useState<number | undefined>(undefined);
  const showSkeleton = !motions || isLoading || isFetching;

  const data = [
    {
      name: 'Completed',
      value: motions?.by_status.completed ?? 0,
      fill: MOTION_STATUS_COLORS.completed,
    },
    { name: 'Pending', value: motions?.by_status.pending ?? 0, fill: MOTION_STATUS_COLORS.pending },
    { name: 'Failed', value: motions?.by_status.failed ?? 0, fill: MOTION_STATUS_COLORS.failed },
    {
      name: 'Cancelled',
      value: motions?.by_status.cancelled ?? 0,
      fill: MOTION_STATUS_COLORS.cancelled,
    },
  ];
  const visibleData = data.filter((item) => item.value > 0);
  const total = motions?.total ?? 0;
  const hasData = total > 0;
  const activeIndex = activeLegendIndex ?? activeSliceIndex;

  return (
    <SectionCard
      className="h-full"
      title={
        <div className="flex items-center gap-2">
          <FiCheckCircle className="h-4 w-4 text-app-accent" />
          <span>Motion Status</span>
        </div>
      }
    >
      {showSkeleton ? (
        <div className="flex h-full flex-1 flex-col gap-3">
          <div className="mx-auto">
            <AnalyticsBodySkeleton className="h-[208px] w-[228px] rounded-full" />
          </div>

          <div className="grid gap-3 min-[480px]:grid-cols-2">
            {Array.from({ length: 4 }).map((_, index) => (
              <div
                key={index}
                className="rounded-2xl bg-surface-muted/70 px-4 py-3"
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="flex min-w-0 items-start gap-3">
                    <span className="mt-1 h-3 w-3 shrink-0 rounded-full bg-border/80" />
                    <InlineValueSkeleton className="h-5 w-20" />
                  </div>
                  <InlineValueSkeleton className="h-8 w-8 shrink-0" />
                </div>
                <InlineValueSkeleton className="mt-1.5 h-3 w-24" />
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
                  data={visibleData}
                  dataKey="value"
                  nameKey="name"
                  innerRadius={58}
                  outerRadius={88}
                  onMouseEnter={(_, index) => setActiveSliceIndex(index)}
                  onMouseLeave={() => setActiveSliceIndex(undefined)}
                  shape={(props) =>
                    renderStatusShape(
                      props as PieSectorProps,
                      (props as PieSectorProps).index === activeIndex
                    )
                  }
                  paddingAngle={3}
                  stroke="none"
                >
                  {visibleData.map((entry) => (
                    <Cell key={entry.name} fill={entry.fill} />
                  ))}
                </Pie>
                <Tooltip
                  content={<AnalyticsChartTooltip />}
                  wrapperStyle={chartTooltipWrapperStyle}
                />
              </PieChart>
            </ResponsiveContainer>
            <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
              <span className="text-[10px] font-bold uppercase tracking-[0.18em] text-subtle">
                Motions
              </span>
              <span className="mt-1 font-poppins text-3xl font-bold text-text">
                {formatCompactNumber(total)}
              </span>
            </div>
          </div>

          <div className="grid gap-3 min-[480px]:grid-cols-2">
            {visibleData.map((item, index) => {
              const percentage = total > 0 ? Math.round((item.value / total) * 100) : 0;
              return (
                <div
                  key={item.name}
                  className={`cursor-pointer rounded-2xl px-3 py-2.5 transition-colors ${
                    activeIndex === index ? 'bg-app-accent-soft shadow-sm' : 'bg-surface-muted/70'
                  }`}
                  onMouseEnter={() => setActiveLegendIndex(index)}
                  onMouseLeave={() => setActiveLegendIndex(undefined)}
                >
                  <p className="text-[13px] font-semibold leading-5 text-text-secondary">{item.name}</p>
                  <div className="mt-1 flex items-center gap-2">
                    <span
                      className="h-3 w-3 shrink-0 rounded-full"
                      style={{ backgroundColor: item.fill }}
                    />
                    <span className="font-poppins text-[18px] font-bold leading-none text-text md:text-[20px]">
                      {formatCompactNumber(item.value)}
                    </span>
                  </div>
                  <p className="mt-1 text-[11px] leading-4 text-subtle">{percentage}% of volume</p>
                </div>
              );
            })}
          </div>
        </div>
      ) : (
        <div className="flex h-full flex-1 flex-col items-center justify-center rounded-2xl bg-surface-muted/70 text-center">
          <p className="text-sm font-semibold text-text-secondary">
            No motion status activity in this period yet
          </p>
          <p className="mt-2 max-w-xs text-xs text-subtle">
            Motion status distribution will appear here once drafted motion records exist for the
            selected period.
          </p>
        </div>
      )}
    </SectionCard>
  );
};
