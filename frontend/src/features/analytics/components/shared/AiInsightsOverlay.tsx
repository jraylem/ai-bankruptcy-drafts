import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  FiActivity,
  FiBarChart2,
  FiCpu,
  FiMessageSquare,
  FiPieChart,
  FiTarget,
  FiTrendingUp,
  FiUsers,
  FiX,
} from 'react-icons/fi';
import { SkeletonBlock } from '../AnalyticsSkeleton';
import { useDashboardInsights } from '../../hooks/useDashboardInsights';
import { useAnalyticsAiChatStore } from '../../stores/useAnalyticsAiChatStore';
import { useAnalyticsFiltersStore } from '../../stores/useAnalyticsFiltersStore';
import type { AnalyticsRangePreset, DashboardInsightPeriodMetric } from '../../types/dashboard.types';

const RANGE_LABELS: Record<AnalyticsRangePreset, string> = {
  today: 'today',
  '7d': 'the last 7 days',
  '30d': 'the last 30 days',
  custom: 'the selected period',
};

const resolveInsightIcon = (type: string) => {
  if (type === 'trend') return <FiTrendingUp className="h-5 w-5" />;
  if (type === 'chart') return <FiBarChart2 className="h-5 w-5" />;
  if (type === 'pie') return <FiPieChart className="h-5 w-5" />;
  if (type === 'users') return <FiUsers className="h-5 w-5" />;
  if (type === 'target') return <FiTarget className="h-5 w-5" />;
  return <FiActivity className="h-5 w-5" />;
};

const resolveSuggestedActionIcon = (actionLabel: string, index: number) => {
  const normalizedLabel = actionLabel.toLowerCase();

  if (
    normalizedLabel.includes('trend') ||
    normalizedLabel.includes('growth') ||
    normalizedLabel.includes('increase') ||
    normalizedLabel.includes('decrease')
  ) {
    return <FiTrendingUp className="h-5 w-5 text-app-accent-text" />;
  }

  if (
    normalizedLabel.includes('chart') ||
    normalizedLabel.includes('breakdown') ||
    normalizedLabel.includes('distribution') ||
    normalizedLabel.includes('compare')
  ) {
    return <FiBarChart2 className="h-5 w-5 text-app-accent-text" />;
  }

  if (
    normalizedLabel.includes('share') ||
    normalizedLabel.includes('ratio') ||
    normalizedLabel.includes('mix')
  ) {
    return <FiPieChart className="h-5 w-5 text-app-accent-text" />;
  }

  if (
    normalizedLabel.includes('user') ||
    normalizedLabel.includes('team') ||
    normalizedLabel.includes('staff')
  ) {
    return <FiUsers className="h-5 w-5 text-app-accent-text" />;
  }

  if (
    normalizedLabel.includes('goal') ||
    normalizedLabel.includes('target') ||
    normalizedLabel.includes('optimize') ||
    normalizedLabel.includes('improve')
  ) {
    return <FiTarget className="h-5 w-5 text-app-accent-text" />;
  }

  const fallbackIcons = [
    <FiActivity key="activity" className="h-5 w-5 text-app-accent-text" />,
    <FiTrendingUp key="trend" className="h-5 w-5 text-app-accent-text" />,
    <FiBarChart2 key="bar" className="h-5 w-5 text-app-accent-text" />,
    <FiPieChart key="pie" className="h-5 w-5 text-app-accent-text" />,
    <FiUsers key="users" className="h-5 w-5 text-app-accent-text" />,
    <FiTarget key="target" className="h-5 w-5 text-app-accent-text" />,
  ];

  return fallbackIcons[index % fallbackIcons.length];
};

const getMetricTrendValue = (metric: DashboardInsightPeriodMetric) => {
  if (typeof metric.pct !== 'number') {
    if (metric.direction === 'flat') return '0%';
    return 'N/A';
  }

  return `${metric.pct}%`;
};

const ComparisonCard: React.FC<{
  label: string;
  value: string;
  trend: 'up' | 'down' | 'flat';
}> = ({ label, value, trend }) => (
  <div className="rounded-xl border border-border/70 bg-surface-muted/60 p-3">
    <p className="text-[10px] font-bold uppercase tracking-[0.14em] text-subtle">{label}</p>
    <p
      className={`mt-1.5 font-poppins text-[18px] font-bold leading-none tracking-tight ${
        trend === 'up'
          ? 'text-app-success-text'
          : trend === 'down'
            ? 'text-app-danger-text'
            : 'text-subtle'
      }`}
    >
      {trend === 'up' ? '▲' : trend === 'down' ? '▼' : '•'} {value}
    </p>
  </div>
);

export const AiInsightsOverlay: React.FC = () => {
  const ICON_SCALE_RESET_MS = 380;
  const [isOpen, setIsOpen] = useState(false);
  const [isMounted, setIsMounted] = useState(false);
  const [iconSpinTurns, setIconSpinTurns] = useState(0);
  const [iconScale, setIconScale] = useState(1);
  const containerRef = useRef<HTMLDivElement>(null);
  const iconScaleTimeoutRef = useRef<number | null>(null);
  const { data: insightsData, isLoading, isError, error } = useDashboardInsights(isOpen);
  const { rangePreset } = useAnalyticsFiltersStore();
  const { openWidget, restoreWidget, enqueueSuggestedAction } = useAnalyticsAiChatStore();

  const activeRangeLabel = RANGE_LABELS[rangePreset];
  const summaryTitle = insightsData?.summary_title || `Trend summary for ${activeRangeLabel}`;

  const periodCards = useMemo(() => {
    if (!insightsData?.period_over_period) {
      return [];
    }

    const pop = insightsData.period_over_period;
    const withValue = (metric: DashboardInsightPeriodMetric) => typeof metric.pct === 'number';
    const cards: Array<{ label: string; metric: DashboardInsightPeriodMetric }> = [
      { label: 'Total Cases', metric: pop.total_cases },
      { label: 'Motions Drafted', metric: pop.motions_drafted },
    ];

    if (pop.orders_drafted) {
      cards.push({ label: 'Orders Drafted', metric: pop.orders_drafted });
    }

    cards.push({ label: 'Active Cases', metric: pop.active_cases });
    cards.push({ label: 'New Users', metric: pop.new_users });
    return cards.filter((card) => withValue(card.metric));
  }, [insightsData]);

  const animateTriggerIcon = useCallback((direction: 'open' | 'close') => {
    setIconSpinTurns((previous) => previous + (direction === 'open' ? 1 : -1));
    setIconScale(1.14);
    if (iconScaleTimeoutRef.current !== null) {
      window.clearTimeout(iconScaleTimeoutRef.current);
    }
    iconScaleTimeoutRef.current = window.setTimeout(() => {
      setIconScale(1);
      iconScaleTimeoutRef.current = null;
    }, ICON_SCALE_RESET_MS);
  }, []);

  const openInsights = useCallback(() => {
    animateTriggerIcon('open');
    setIsMounted(true);
    window.requestAnimationFrame(() => setIsOpen(true));
  }, [animateTriggerIcon]);

  const closeOverlay = useCallback(() => {
    animateTriggerIcon('close');
    setIsOpen(false);
  }, [animateTriggerIcon]);

  const openChatWidget = useCallback(() => {
    restoreWidget();
    openWidget();
    closeOverlay();
  }, [closeOverlay, openWidget, restoreWidget]);

  const handleSuggestedActionClick = useCallback(
    (actionLabel: string) => {
      enqueueSuggestedAction(actionLabel);
      closeOverlay();
    },
    [closeOverlay, enqueueSuggestedAction]
  );

  useEffect(() => {
    if (!isOpen) return;

    const handleClickOutside = (event: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        closeOverlay();
      }
    };

    const handleEscapeKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        closeOverlay();
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    document.addEventListener('keydown', handleEscapeKey);

    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
      document.removeEventListener('keydown', handleEscapeKey);
    };
  }, [closeOverlay, isOpen]);

  useEffect(() => {
    return () => {
      if (iconScaleTimeoutRef.current !== null) {
        window.clearTimeout(iconScaleTimeoutRef.current);
      }
    };
  }, []);

  return (
    <div ref={containerRef} className="relative z-30">
      <button
        type="button"
        onClick={() => {
          if (isOpen) {
            closeOverlay();
          } else {
            openInsights();
          }
        }}
        className="inline-flex h-[42px] items-center gap-2 rounded-full bg-surface/95 px-4 text-sm font-semibold tracking-tight text-text shadow-[0_12px_28px_rgba(15,23,42,0.12)] transition-colors hover:bg-surface-muted/80"
      >
        <span
          className="inline-block text-violet-600 transition-transform duration-300 ease-out"
          style={{ transform: `rotate(${iconSpinTurns * 360}deg) scale(${iconScale})` }}
        >
          ✦
        </span>
        AI Insights
      </button>

      {isMounted ? (
        <section
          aria-label="AI insights modal"
          className={`absolute left-0 top-[56px] z-40 max-h-[78vh] w-[460px] max-w-[calc(100vw-2rem)] overflow-y-auto rounded-2xl bg-surface/95 px-5 py-4 shadow-[0_24px_48px_rgba(15,23,42,0.22)] backdrop-blur-xl transition-all duration-200 ease-out ${
            isOpen ? 'translate-y-0 opacity-100' : 'pointer-events-none -translate-y-1 opacity-0'
          }`}
        >
          <div className="flex items-start justify-between gap-3">
            <div className="flex gap-3">
              <FiCpu className="h-6 w-6 text-text-secondary" />
              <div>
                <p className="inline-flex items-center gap-1.5 text-sm font-medium font-poppins">
                  {summaryTitle}
                  <span className="inline-block animate-insight-beat text-app-accent-text">✦</span>
                </p>
              </div>
            </div>

            <button
              type="button"
              onClick={closeOverlay}
              className="rounded-full p-2 text-muted transition hover:bg-surface-muted/80 hover:text-text"
              aria-label="Close AI insights"
            >
              <FiX className="h-4 w-4" />
            </button>
          </div>

          {isLoading ? (
            <div className="mt-4 space-y-3">
              {Array.from({ length: 5 }).map((_, index) => (
                <div
                  key={`insight-skeleton-${index}`}
                  className="grid grid-cols-[30px_1fr] items-center gap-3 rounded-xl border border-border/80 bg-surface-muted/70 px-3.5 py-2.5"
                >
                  <SkeletonBlock className="h-5 w-5 rounded-md" />
                  <div>
                    <SkeletonBlock className="h-3.5 w-full rounded-lg" />
                    <SkeletonBlock className="mt-1.5 h-3.5 w-[78%] rounded-lg" />
                  </div>
                </div>
              ))}

              <div className="pt-1">
                <SkeletonBlock className="h-6 w-[72%] rounded-lg" />
              </div>

              <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
                {Array.from({ length: 3 }).map((_, index) => (
                  <div key={`metric-skeleton-${index}`} className="rounded-xl border border-border/70 bg-surface-muted/60 p-3">
                    <SkeletonBlock className="h-3 w-[72%] rounded-lg" />
                    <SkeletonBlock className="mt-2 h-6 w-[62%] rounded-lg" />
                  </div>
                ))}
              </div>

              <div className="pt-1">
                <SkeletonBlock className="h-6 w-44 rounded-lg" />
              </div>

              <div className="space-y-2.5">
                {Array.from({ length: 3 }).map((_, index) => (
                  <div
                    key={`action-skeleton-${index}`}
                    className="inline-flex w-full items-center gap-3 rounded-xl border border-border bg-surface-muted/70 px-3.5 py-2.5"
                  >
                    <SkeletonBlock className="h-5 w-5 rounded-md" />
                    <SkeletonBlock className="h-4 w-[68%] rounded-lg" />
                  </div>
                ))}
              </div>
            </div>
          ) : null}

          {isError && !isLoading ? (
            <div className="mt-4 rounded-xl border border-app-danger/40 bg-app-danger-soft/40 px-3.5 py-3 text-sm text-app-danger-text">
              {(error as Error | null)?.message || 'Failed to load AI insights.'}
            </div>
          ) : null}

          {!isLoading ? (
            <>
              <div className="mt-4 space-y-2.5">
                {(insightsData?.insights ?? []).map((item, index) => (
                  <article
                    key={`${item.type}-${index}`}
                    className="grid grid-cols-[30px_1fr] items-center gap-3 rounded-xl border border-border/80 bg-surface-muted/70 px-3.5 py-2.5"
                  >
                    <div className="text-app-accent-text">{resolveInsightIcon(item.type)}</div>
                    <p className="text-sm leading-relaxed tracking-tight text-text-secondary">{item.text}</p>
                  </article>
                ))}
              </div>
              {!isError && (insightsData?.insights?.length ?? 0) === 0 ? (
                <p className="mt-4 rounded-xl border border-border/80 bg-surface-muted/70 px-3.5 py-3 text-sm text-muted">
                  No insights available for this range yet.
                </p>
              ) : null}

              <h4 className="mt-5 text-base font-semibold tracking-tight text-text">
                Period-over-period{' '}
                <span className="text-xs font-medium text-subtle">
                  {insightsData?.period_over_period
                    ? `(${insightsData.period_over_period.current_label} vs ${insightsData.period_over_period.prior_label})`
                    : ''}
                </span>
              </h4>

              <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-3">
                {periodCards.map((card) => (
                  <ComparisonCard
                    key={card.label}
                    label={card.label}
                    value={getMetricTrendValue(card.metric)}
                    trend={
                      card.metric.direction === 'up' || card.metric.direction === 'down'
                        ? card.metric.direction
                        : 'flat'
                    }
                  />
                ))}
              </div>
              {periodCards.length === 0 ? (
                <p className="mt-3 rounded-xl border border-border/80 bg-surface-muted/70 px-3.5 py-3 text-sm text-muted">
                  No comparable period-over-period values for this range.
                </p>
              ) : null}

              <div className="mt-5 flex items-center justify-between gap-2">
                <h4 className="text-base font-semibold tracking-tight text-text">Suggested actions</h4>
                <button
                  type="button"
                  onClick={openChatWidget}
                  className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-surface px-2.5 py-1 text-xs font-medium text-text-secondary transition-colors hover:border-app-accent/60"
                >
                  <FiMessageSquare className="h-3.5 w-3.5" />
                  Open chat
                </button>
              </div>

              <div className="mt-3 space-y-2.5">
                {(insightsData?.suggested_actions ?? []).map((actionLabel, index) => (
                  <button
                    key={`${actionLabel}-${index}`}
                    type="button"
                    onClick={() => handleSuggestedActionClick(actionLabel)}
                    className="inline-flex w-full items-center gap-3 rounded-xl border border-border bg-surface-muted/70 px-3.5 py-2.5 text-sm font-medium tracking-tight text-text-secondary transition-colors hover:border-app-accent/60 hover:bg-surface-muted/90"
                  >
                    {resolveSuggestedActionIcon(actionLabel, index)}
                    {actionLabel}
                  </button>
                ))}
              </div>
              {!isError && (insightsData?.suggested_actions?.length ?? 0) === 0 ? (
                <p className="mt-3 rounded-xl border border-border/80 bg-surface-muted/70 px-3.5 py-3 text-sm text-muted">
                  No suggested actions generated for this range.
                </p>
              ) : null}
            </>
          ) : null}
        </section>
      ) : null}

      <style>{`
        @keyframes insight-beat {
          0%,
          100% {
            transform: scale(1);
          }
          50% {
            transform: scale(1.3);
          }
        }

        .animate-insight-beat {
          animation: insight-beat 1.5s ease-in-out infinite;
          transform-origin: center;
        }
      `}</style>
    </div>
  );
};
