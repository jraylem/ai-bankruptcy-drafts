import React, { useState } from 'react';
import { FiPieChart } from 'react-icons/fi';
import { Cell, Pie, PieChart, ResponsiveContainer, Sector, Tooltip } from 'recharts';
import { useDashboardCases } from '../../hooks/useDashboardCases';
import { AnalyticsBodySkeleton, InlineValueSkeleton } from '../AnalyticsSkeleton';
import { AnalyticsChartTooltip } from '../chartShared';
import { chartTooltipWrapperStyle } from '../chartStyles';
import { formatCompactNumber } from '../../utils/dashboard.mappers';
import { SectionCard } from '../SectionCard';
import { CASE_STATUS_COLORS } from '../../utils/statusVisuals';

type PieSectorProps = React.ComponentProps<typeof Sector> & {
  index?: number;
};

const renderCaseShape = (props: PieSectorProps, isActive: boolean) => {
  const outerRadius = typeof props.outerRadius === 'number' ? props.outerRadius : 72;

  if (!isActive) {
    return <Sector {...props} />;
  }

  return (
    <g>
      <Sector {...props} outerRadius={outerRadius + 5} />
      <Sector
        {...props}
        outerRadius={outerRadius + 8}
        innerRadius={outerRadius + 6}
        fill={props.fill}
        opacity={0.18}
      />
    </g>
  );
};

export const CaseStatusCard: React.FC = () => {
  const { data: cases, isLoading, isFetching } = useDashboardCases();
  const [activeSliceIndex, setActiveSliceIndex] = useState<number | undefined>(undefined);
  const [activeLegendIndex, setActiveLegendIndex] = useState<number | undefined>(undefined);
  const data = [
    { name: 'Active', value: cases?.active_cases.sum ?? 0, fill: CASE_STATUS_COLORS.active },
    { name: 'Pending', value: cases?.pending_cases ?? 0, fill: CASE_STATUS_COLORS.pending },
    { name: 'Denied', value: cases?.inactive_cases.denied ?? 0, fill: CASE_STATUS_COLORS.denied },
    {
      name: 'Archived',
      value: cases?.inactive_cases.archived ?? 0,
      fill: CASE_STATUS_COLORS.archived,
    },
    { name: 'Deleted', value: cases?.inactive_cases.deleted ?? 0, fill: CASE_STATUS_COLORS.deleted },
  ];
  const visibleLegendData = data.filter((item) => item.value > 0);
  const total = cases?.total ?? 0;
  const showSkeleton = !cases || isLoading || isFetching;
  const activeIndex = activeLegendIndex ?? activeSliceIndex;
  return (
    <SectionCard
      title={
        <div className="flex items-center gap-2">
          <FiPieChart className="h-4 w-4 text-app-accent" />
          <span>Case Status</span>
        </div>
      }
    >
      <div className="flex items-center justify-center">
        <div className="analytics-chart-shell relative h-40 w-40">
          {showSkeleton ? (
            <AnalyticsBodySkeleton className="h-40 rounded-full" />
          ) : (
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={data}
                  dataKey="value"
                  innerRadius={52}
                  outerRadius={72}
                  onMouseEnter={(_, index) => setActiveSliceIndex(index)}
                  onMouseLeave={() => setActiveSliceIndex(undefined)}
                  shape={(props) =>
                    renderCaseShape(
                      props as PieSectorProps,
                      (props as PieSectorProps).index === activeIndex
                    )
                  }
                  stroke="none"
                  paddingAngle={2}
                >
                  {data.map((item) => (
                    <Cell key={item.name} fill={item.fill} />
                  ))}
                </Pie>
                <Tooltip
                  content={<AnalyticsChartTooltip />}
                  wrapperStyle={chartTooltipWrapperStyle}
                />
              </PieChart>
            </ResponsiveContainer>
          )}
          <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
            {showSkeleton ? (
              <>
                <InlineValueSkeleton className="h-8 w-16" />
                <InlineValueSkeleton className="mt-2 h-3 w-10" />
              </>
            ) : (
              <>
                <span className="block text-2xl font-bold text-text">
                  {formatCompactNumber(total)}
                </span>
                <span className="text-[10px] font-bold uppercase text-subtle">Total</span>
              </>
            )}
          </div>
        </div>
      </div>
      <div className="mt-4 flex flex-wrap items-center justify-center gap-2 text-[11px] font-bold uppercase text-muted">
        {visibleLegendData.map((item) => {
          const index = data.findIndex((entry) => entry.name === item.name);
          const percent = total > 0 ? Math.round((item.value / total) * 100) : 0;
          return (
            <div
              key={item.name}
              className={`flex min-w-[92px] cursor-pointer items-center justify-between gap-2 rounded-full px-2 py-1 transition-colors ${
                activeIndex === index ? 'bg-surface-muted text-text-secondary shadow-sm' : ''
              }`}
              onMouseEnter={() => setActiveLegendIndex(index)}
              onMouseLeave={() => setActiveLegendIndex(undefined)}
            >
              <div className="flex items-center gap-2">
                <span className="h-2 w-2 rounded-full" style={{ backgroundColor: item.fill }} />
                <span>{item.name}</span>
              </div>
              {showSkeleton ? <InlineValueSkeleton className="h-3 w-8" /> : <span>{percent}%</span>}
            </div>
          );
        })}
      </div>
    </SectionCard>
  );
};
