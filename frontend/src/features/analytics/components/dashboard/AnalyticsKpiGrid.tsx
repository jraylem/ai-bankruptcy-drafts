import React from 'react';
import { useDashboardCases } from '../../hooks/useDashboardCases';
import { useDashboardMotions } from '../../hooks/useDashboardMotions';
import { useDashboardSystemStatus } from '../../hooks/useDashboardSystemStatus';
import { formatCompactNumber } from '../../utils/dashboard.mappers';
import { KpiSurface } from '../KpiSurface';

export const AnalyticsKpiGrid: React.FC = () => {
  const {
    data: cases,
    isLoading: isCasesLoading,
  } = useDashboardCases();
  const {
    data: motions,
    isLoading: isMotionsLoading,
  } = useDashboardMotions();
  const {
    data: systemStatus,
    isLoading: isSystemLoading,
  } = useDashboardSystemStatus();

  const pollHealthy = Boolean(systemStatus?.poll_worker.enabled && systemStatus?.poll_worker.running);
  const queueHealthy = (systemStatus?.task_queue.pending ?? 0) === 0;
  const avgResponseMs = systemStatus?.avg_response.avg_ms ?? 0;
  const queuePending = systemStatus?.task_queue.pending ?? 0;
  const errors24h = systemStatus?.errors.count_24h ?? 0;
  const pollEnabled = Boolean(systemStatus?.poll_worker.enabled);
  const pollRunning = Boolean(systemStatus?.poll_worker.running);
  const avgResponseLabel = Number.isFinite(avgResponseMs)
    ? `${Math.round(avgResponseMs)}ms`
    : 'N/A';

  const criticalReasons: string[] = [];
  if (!pollHealthy) {
    if (!pollEnabled) {
      criticalReasons.push('Poll worker disabled');
    } else if (!pollRunning) {
      criticalReasons.push('Poll worker stopped');
    } else {
      criticalReasons.push('Poll worker unhealthy');
    }
  }

  const degradedReasons: string[] = [];
  if (!queueHealthy) {
    degradedReasons.push(`Queue backlog: ${formatCompactNumber(queuePending)}`);
  }
  if (avgResponseMs > 1200) {
    degradedReasons.push(`Avg API response: ${avgResponseLabel}`);
  }
  if (errors24h > 0) {
    degradedReasons.push(`Errors (24h): ${formatCompactNumber(errors24h)}`);
  }

  const systemHealthKpi =
    !systemStatus
      ? {
          value: '--',
          valueClass: 'text-subtle',
          helperText: 'Tracking worker, queue, latency, and errors',
        }
      : !pollHealthy
      ? {
          value: 'Critical',
          valueClass: 'text-app-danger-text',
          helperText: criticalReasons.join(' · ') || 'Critical service issue detected',
        }
      : !queueHealthy || avgResponseMs > 1200 || errors24h > 0
        ? {
            value: 'Degraded',
            valueClass: 'text-app-warning-text',
            helperText: degradedReasons.join(' · ') || 'Performance issue detected',
          }
        : {
            value: 'Healthy',
            valueClass: 'text-app-success-text',
            helperText: `Poll worker running · Avg API response: ${avgResponseLabel}`,
          };

  const cards = [
    {
      label: 'Total Cases',
      value: cases ? formatCompactNumber(cases.total) : '--',
      iconKey: 'totalCases' as const,
      helperText: 'All cases created in selected period',
      loading: isCasesLoading && !cases,
    },
    {
      label: 'Active Cases',
      value: cases ? formatCompactNumber(cases.active_cases.sum) : '--',
      iconKey: 'activeCases' as const,
      valueClass: 'text-app-success-text',
      helperText: 'Cases currently marked active',
      loading: isCasesLoading && !cases,
    },
    {
      label: 'Pending Cases',
      value: cases ? formatCompactNumber(cases.pending_cases) : '--',
      iconKey: 'pendingCases' as const,
      valueClass: 'text-app-warning-text',
      helperText: 'Cases waiting for acceptance or review',
      loading: isCasesLoading && !cases,
    },
    {
      label: 'Motions Drafted',
      value: motions ? formatCompactNumber(motions.total) : '--',
      iconKey: 'motionsDrafted' as const,
      valueClass: 'text-app-accent-text',
      helperText: 'All motions drafted in selected period',
      loading: isMotionsLoading && !motions,
    },
    {
      label: 'Motions Pending',
      value: motions ? formatCompactNumber(motions.by_status.pending) : '--',
      iconKey: 'pendingCases' as const,
      valueClass: 'text-app-warning-text',
      helperText: 'Drafted motions still pending',
      loading: isMotionsLoading && !motions,
    },
    {
      label: 'System Health',
      value: systemHealthKpi.value,
      iconKey: 'systemStatus' as const,
      valueClass: systemHealthKpi.valueClass,
      helperText: systemHealthKpi.helperText,
      loading: isSystemLoading && !systemStatus,
    },
  ];

  return (
    <section className="mb-8">
      <div className="grid grid-cols-2 gap-4 md:grid-cols-3 xl:grid-cols-6">
        {cards.map((card) => (
          <KpiSurface key={card.label} {...card} loading={card.loading} />
        ))}
      </div>
    </section>
  );
};
