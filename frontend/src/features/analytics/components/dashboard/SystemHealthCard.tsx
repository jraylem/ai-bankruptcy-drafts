import React from 'react';
import { FiShield } from 'react-icons/fi';
import { AnalyticsBodySkeleton, InlineValueSkeleton } from '../AnalyticsSkeleton';
import { SectionCard } from '../SectionCard';
import { useDashboardSystemStatus } from '../../hooks/useDashboardSystemStatus';
import { formatAnalyticsNumber } from '../../utils/dashboard.mappers';

const formatRelativeHealthTime = (value?: string) => {
  if (!value) return 'No recent run';

  const timestamp = new Date(value).getTime();
  if (Number.isNaN(timestamp)) return 'No recent run';

  const diffMinutes = Math.max(0, Math.floor((Date.now() - timestamp) / 60_000));

  if (diffMinutes < 1) return 'Just now';
  if (diffMinutes < 60) return `${diffMinutes} min${diffMinutes === 1 ? '' : 's'} ago`;

  const diffHours = Math.floor(diffMinutes / 60);
  if (diffHours < 24) return `${diffHours} hr${diffHours === 1 ? '' : 's'} ago`;

  const diffDays = Math.floor(diffHours / 24);
  if (diffDays < 7) return `${diffDays} day${diffDays === 1 ? '' : 's'} ago`;

  return new Date(value).toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  });
};

export const SystemHealthCard: React.FC = () => {
  const { data, isLoading, isFetching } = useDashboardSystemStatus();
  const showSkeleton = !data && (isLoading || isFetching);
  const queueHealthy = (data?.task_queue.pending ?? 0) === 0;
  const pollHealthy = Boolean(data?.poll_worker.enabled && data?.poll_worker.running);
  const errorDelta = data?.errors.delta_from_yesterday ?? 0;
  const errors24h = data?.errors.count_24h ?? 0;
  const avgResponseMs = data?.avg_response.avg_ms ?? 0;
  const errorTrendLabel =
    errorDelta > 0
      ? `+${formatAnalyticsNumber(errorDelta, { maximumFractionDigits: 0 })} vs yesterday`
      : errorDelta < 0
        ? `${formatAnalyticsNumber(errorDelta, { maximumFractionDigits: 0 })} vs yesterday`
        : 'No change vs yesterday';
  const pollLastRunLabel = formatRelativeHealthTime(data?.poll_worker.last_run_at);
  const responseHealth =
    avgResponseMs <= 500
      ? { label: 'Healthy', className: 'bg-app-success-soft text-app-success-text' }
      : avgResponseMs <= 1200
        ? { label: 'Elevated', className: 'bg-app-warning-soft text-app-warning-text' }
        : { label: 'Slow', className: 'bg-app-danger-soft text-app-danger-text' };
  const errorSignalHealthy = errors24h === 0;

  return (
    <SectionCard
      className="h-full"
      headerClassName="items-start"
      title={
        <div>
          <div className="flex items-center gap-2">
            <FiShield className="h-4 w-4 text-app-accent" />
            <span>System Health</span>
          </div>
          <p className="mt-1 text-xs font-normal text-subtle">
            Worker, queue, error, and API performance status.
          </p>
        </div>
      }
    >
      <div className="mb-4 grid grid-cols-3 gap-4">
        {[
          {
            label: 'Task Queue',
            status: queueHealthy ? 'Operational' : 'Backlog',
            dotClass: queueHealthy
              ? 'bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.5)]'
              : 'bg-amber-500 shadow-[0_0_8px_rgba(245,158,11,0.45)]',
            meta: null,
          },
          {
            label: 'Poll Worker',
            status: pollHealthy ? 'Running' : 'Stopped',
            dotClass: pollHealthy
              ? 'bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.5)]'
              : 'bg-rose-500 shadow-[0_0_8px_rgba(244,63,94,0.5)]',
            meta: showSkeleton ? null : `Last run ${pollLastRunLabel}`,
          },
          {
            label: 'Error Signal',
            status: errorSignalHealthy ? 'Clean' : 'Has Errors',
            dotClass: errorSignalHealthy
              ? 'bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.5)]'
              : 'bg-amber-500 shadow-[0_0_8px_rgba(245,158,11,0.45)]',
            meta: showSkeleton
              ? null
              : `${formatAnalyticsNumber(errors24h, {
                  maximumFractionDigits: 0,
                })} in last 24 hours`,
          },
        ].map((item) => (
          <div
            key={item.label}
            className="flex min-h-[88px] flex-col justify-center rounded-[18px] bg-surface-muted/70 px-4 py-3 text-center"
          >
            <div className={`mx-auto mb-2 h-2 w-2 rounded-full ${item.dotClass}`} />
            <p className="text-[10px] font-bold uppercase text-muted">{item.label}</p>
            <p className="mt-1 text-xs font-semibold text-text">{item.status}</p>
            {item.meta ? (
              <p className="mt-1 truncate text-[10px] font-medium text-subtle">{item.meta}</p>
            ) : (
              <span className="mt-1 block h-[14px]" aria-hidden="true" />
            )}
          </div>
        ))}
      </div>

      <div className="space-y-4 border-t border-border/50 pt-2">
        <div className="flex items-center justify-between">
          <div>
            <span className="text-sm font-semibold text-text-secondary">Response Health</span>
            <p className="text-[11px] text-subtle">Uses average API response time</p>
          </div>
          {showSkeleton ? (
            <div className="flex flex-col items-center gap-1">
              <InlineValueSkeleton className="h-4 w-14" />
              <InlineValueSkeleton className="h-6 w-16 rounded-full" />
            </div>
          ) : (
            <div className="flex flex-col items-center gap-1">
              <span className="text-sm font-bold text-app-accent-text">
                {formatAnalyticsNumber(avgResponseMs, { maximumFractionDigits: 1 })} ms
              </span>
              <span
                className={`rounded-full px-2.5 py-1 text-[11px] font-semibold ${responseHealth.className}`}
              >
                {responseHealth.label}
              </span>
            </div>
          )}
        </div>
        <div className="space-y-2 pt-2">
          <p className="text-[10px] font-bold uppercase tracking-[0.18em] text-subtle">
            Operational Metrics
          </p>
          {showSkeleton ? (
            <div className="grid grid-cols-2 gap-2">
              <AnalyticsBodySkeleton className="h-[79px] rounded-2xl" />
              <AnalyticsBodySkeleton className="h-[79px] rounded-2xl" />
              <AnalyticsBodySkeleton className="h-[79px] rounded-2xl" />
              <AnalyticsBodySkeleton className="h-[79px] rounded-2xl" />
            </div>
          ) : (
            <div className="grid grid-cols-2 gap-2">
              <div className="flex min-h-[79px] flex-col justify-between rounded-2xl bg-surface-muted/70 px-3 py-2.5">
                <p className="text-[10px] font-bold uppercase tracking-[0.14em] text-subtle">
                  Queue Pending
                </p>
                <p className="font-poppins text-2xl font-bold text-text">
                  {formatAnalyticsNumber(data?.task_queue.pending ?? 0, {
                    maximumFractionDigits: 0,
                  })}
                </p>
              </div>
              <div className="flex min-h-[79px] flex-col justify-between rounded-2xl bg-surface-muted/70 px-3 py-2.5">
                <p className="text-[10px] font-bold uppercase tracking-[0.14em] text-subtle">
                  Active Tasks
                </p>
                <p className="font-poppins text-2xl font-bold text-text">
                  {formatAnalyticsNumber(data?.task_queue.active ?? 0, {
                    maximumFractionDigits: 0,
                  })}
                </p>
              </div>
              <div className="flex min-h-[79px] flex-col justify-between rounded-2xl bg-surface-muted/70 px-3 py-2.5">
                <p className="text-[10px] font-bold uppercase tracking-[0.14em] text-subtle">
                  Errors (24h)
                </p>
                <div className="mt-1 flex items-end justify-between gap-2">
                  <p className="font-poppins text-2xl font-bold text-text">
                    {formatAnalyticsNumber(data?.errors.count_24h ?? 0, {
                      maximumFractionDigits: 0,
                    })}
                  </p>
                  <p
                    className={`text-[11px] font-medium ${
                      errorDelta > 0
                        ? 'text-app-warning-text'
                        : errorDelta < 0
                          ? 'text-app-success-text'
                          : 'text-subtle'
                    }`}
                  >
                    {errorTrendLabel}
                  </p>
                </div>
              </div>
              <div className="flex min-h-[79px] flex-col justify-between rounded-2xl bg-surface-muted/70 px-3 py-2.5">
                <p className="text-[10px] font-bold uppercase tracking-[0.14em] text-subtle">
                  P95 Response
                </p>
                <p className="font-poppins text-2xl font-bold text-text">
                  {formatAnalyticsNumber(data?.avg_response.p95_ms ?? 0, {
                    maximumFractionDigits: 1,
                  })}{' '}
                  ms
                </p>
              </div>
            </div>
          )}
        </div>
      </div>
    </SectionCard>
  );
};
