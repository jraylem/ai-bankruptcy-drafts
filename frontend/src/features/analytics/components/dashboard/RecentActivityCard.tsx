import React, { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  FiActivity,
  FiAlertCircle,
  FiCheckCircle,
  FiChevronLeft,
  FiChevronRight,
  FiClock,
  FiDownload,
  FiFileText,
  FiInbox,
  FiLogIn,
  FiRefreshCw,
  FiServer,
  FiUploadCloud,
  FiUsers,
} from 'react-icons/fi';
import { Modal, SelectDropdown } from '@/components/common';
import { useDashboardActivityActions } from '../../hooks/useDashboardActivityActions';
import { useDashboardActivityFeed } from '../../hooks/useDashboardActivityFeed';
import type { ActivityIconKey, ActivityTone } from '../../utils/activityFeed.helpers';
import {
  formatActivityLabel,
  formatActivityDetails,
  getActivityHighlights,
  formatRelativeActivityTime,
  getActivityIconKey,
  getActivityTone,
} from '../../utils/activityFeed.helpers';
import { AnalyticsBodySkeleton } from '../AnalyticsSkeleton';
import { SectionCard } from '../SectionCard';

const toneClasses: Record<ActivityTone, string> = {
  indigo: 'bg-app-accent-soft text-app-accent-text',
  amber: 'bg-app-warning-soft text-app-warning-text',
  emerald: 'bg-app-success-soft text-app-success-text',
  rose: 'bg-app-danger-soft text-app-danger-text',
};

const renderActivityIcon = (iconKey: ActivityIconKey) => {
  switch (iconKey) {
    case 'alert':
      return <FiAlertCircle className="h-5 w-5" />;
    case 'check':
      return <FiCheckCircle className="h-5 w-5" />;
    case 'clock':
      return <FiClock className="h-5 w-5" />;
    case 'download':
      return <FiDownload className="h-5 w-5" />;
    case 'file':
      return <FiFileText className="h-5 w-5" />;
    case 'inbox':
      return <FiInbox className="h-5 w-5" />;
    case 'login':
      return <FiLogIn className="h-5 w-5" />;
    case 'refresh':
      return <FiRefreshCw className="h-5 w-5" />;
    case 'server':
      return <FiServer className="h-5 w-5" />;
    case 'upload':
      return <FiUploadCloud className="h-5 w-5" />;
    case 'users':
      return <FiUsers className="h-5 w-5" />;
    default:
      return <FiActivity className="h-5 w-5" />;
  }
};

const ActivityFeedRow: React.FC<{
  action: string;
  label: string;
  meta: string;
  time: string;
  highlights?: string[];
  compact?: boolean;
}> = ({ action, label, meta, time, highlights = [], compact = false }) => {
  const tone = getActivityTone(action);
  const iconKey = getActivityIconKey(action);

  return (
    <div
      className={`group flex gap-4 rounded-xl bg-surface ${
        compact
          ? 'items-start p-2 transition-colors hover:bg-activity-row-hover'
          : 'items-center border border-border/50 px-4 py-3 transition-colors hover:bg-activity-row-hover'
      }`}
    >
      <div
        className={`mt-0.5 flex h-10 w-10 items-center justify-center rounded-full ${toneClasses[tone]}`}
      >
        {renderActivityIcon(iconKey)}
      </div>

      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium text-text">{label}</p>
        <p className={`mt-1 text-xs text-subtle ${compact ? 'line-clamp-2' : ''}`}>{meta}</p>
        {compact ? (
          <div className="mt-2 flex flex-col gap-1.5 sm:hidden">
            {highlights.length > 0 ? (
              <div className="flex flex-wrap gap-1.5">
                {highlights.map((highlight) => (
                  <span
                    key={highlight}
                    className="rounded-full border border-border bg-surface-muted/70 px-2 py-0.5 text-[10px] text-muted"
                  >
                    {highlight}
                  </span>
                ))}
              </div>
            ) : null}
            <p className="text-[11px] text-subtle">{time}</p>
          </div>
        ) : null}
      </div>
      {highlights.length > 0 || Boolean(time) ? (
        <div
          className={`ml-auto flex flex-col items-end gap-1.5 self-center ${
            compact ? 'hidden max-w-[45%] sm:flex' : 'max-w-[46%]'
          }`}
        >
          {highlights.length > 0 ? (
            <div className="flex flex-wrap justify-end gap-1.5">
              {highlights.map((highlight) => (
                <span
                  key={highlight}
                  className={`rounded-full border border-border bg-surface-muted/70 text-muted ${
                    compact ? 'px-2 py-0.5 text-[10px]' : 'px-2.5 py-1 text-[11px]'
                  }`}
                >
                  {highlight}
                </span>
              ))}
            </div>
          ) : null}
          <p className={compact ? 'text-[11px] text-subtle' : 'text-xs text-subtle'}>{time}</p>
        </div>
      ) : null}
    </div>
  );
};

const ActivityFeedModal: React.FC<{
  isOpen: boolean;
  onClose: () => void;
}> = ({ isOpen, onClose }) => {
  const [selectedAction, setSelectedAction] = useState('');
  const [page, setPage] = useState(1);
  const limit = 20;
  const offset = (page - 1) * limit;
  const { data: actionOptionsData } = useDashboardActivityActions(isOpen);
  const { data, isLoading, isFetching } = useDashboardActivityFeed({
    action: selectedAction || undefined,
    limit,
    offset,
  });

  const filterOptions = useMemo(
    () => [{ label: 'All actions', value: '' }, ...(actionOptionsData ?? [])],
    [actionOptionsData]
  );
  const total = data?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / limit));
  const rows = data?.items ?? [];
  const showSkeleton = !data || isLoading || isFetching;

  const handleActionChange = (value: string) => {
    setSelectedAction(value);
    setPage(1);
  };

  return (
    <Modal isOpen={isOpen} onClose={onClose} size="3xl">
      <div className="flex h-[80vh] flex-col bg-surface">
        <div className="border-b border-border px-6 py-5">
          <div className="flex flex-col gap-4 pr-8 sm:flex-row sm:items-start sm:justify-between">
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-3">
                <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-app-accent-soft text-app-accent-text">
                  <FiActivity className="h-5 w-5" />
                </div>
                <div>
                  <h3 className="text-xl font-semibold text-text">Recent Activity</h3>
                  <p className="mt-1 text-sm text-muted">
                    Monitor the latest uploads, reviews, downloads, and system actions.
                  </p>
                </div>
              </div>
            </div>

            <div className="min-w-[260px] sm:max-w-[320px]">
              <label className="mb-1 block text-[11px] font-bold uppercase tracking-[0.14em] text-subtle">
                Filter Actions
              </label>
              <SelectDropdown
                value={selectedAction}
                onChange={handleActionChange}
                options={filterOptions}
                placeholder="All actions"
                className="w-full"
              />
            </div>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto bg-surface-muted px-6 py-5">
          {showSkeleton ? (
            <AnalyticsBodySkeleton className="h-full" />
          ) : rows.length === 0 ? (
            <div className="flex h-full min-h-[360px] flex-col items-center justify-center rounded-2xl bg-surface-muted/70 text-center">
              <FiClock className="h-8 w-8 text-border" />
              <p className="mt-4 text-sm font-semibold text-text-secondary">No activity found</p>
              <p className="mt-2 max-w-xs text-xs text-subtle">
                Try a different filter or widen the selected analytics date range.
              </p>
            </div>
          ) : (
            <div className="space-y-1">
              {rows.map((row) => (
                <ActivityFeedRow
                  key={row.id}
                  action={row.action}
                  label={formatActivityLabel(row)}
                  meta={formatActivityDetails(row)}
                  time={formatRelativeActivityTime(row.occurred_at)}
                  highlights={getActivityHighlights(row, 4)}
                />
              ))}
            </div>
          )}
        </div>

        <div className="border-t border-border bg-surface px-6 py-4">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
            <p className="text-sm text-muted">
              {total > 0
                ? `Showing ${offset + 1}-${Math.min(offset + rows.length, total)} of ${total} activities`
                : 'No events to display'}
            </p>

            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => setPage((current) => Math.max(1, current - 1))}
                disabled={page === 1}
                className="inline-flex items-center gap-2 rounded-xl border border-border px-3 py-2 text-sm font-medium text-text-secondary transition hover:bg-surface-muted/70 disabled:cursor-not-allowed disabled:opacity-50"
              >
                <FiChevronLeft className="h-4 w-4" />
                Prev
              </button>
              <span className="min-w-[84px] text-center text-sm font-medium text-text-secondary">
                Page {page} of {totalPages}
              </span>
              <button
                type="button"
                onClick={() => setPage((current) => Math.min(totalPages, current + 1))}
                disabled={page >= totalPages}
                className="inline-flex items-center gap-2 rounded-xl border border-border px-3 py-2 text-sm font-medium text-text-secondary transition hover:bg-surface-muted/70 disabled:cursor-not-allowed disabled:opacity-50"
              >
                Next
                <FiChevronRight className="h-4 w-4" />
              </button>
            </div>
          </div>
        </div>
      </div>
    </Modal>
  );
};

export const RecentActivityCard: React.FC = () => {
  const navigate = useNavigate();
  const [isModalOpen, setIsModalOpen] = useState(false);
  const { data, isLoading, isFetching } = useDashboardActivityFeed({ limit: 5, offset: 0 });
  const rows = data?.items ?? [];
  const showSkeleton = !data || isLoading || isFetching;

  return (
    <>
      <SectionCard
        className="h-full"
        title={
          <div className="flex items-center gap-2">
            <FiActivity className="h-4 w-4 text-app-accent" />
            <span>Recent Activity</span>
          </div>
        }
        action={
          !showSkeleton && rows.length > 0 ? (
            <button
              type="button"
              onClick={() => navigate('/analytics/activity-log')}
              className="rounded-full border border-border px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.12em] text-muted transition hover:border-app-accent hover:text-app-accent-text"
            >
              View All
            </button>
          ) : null
        }
      >
        {showSkeleton ? (
          <AnalyticsBodySkeleton className="h-[260px]" />
        ) : rows.length === 0 ? (
          <div className="flex h-[260px] flex-col items-center justify-center rounded-2xl bg-surface-muted/70 text-center">
            <FiClock className="h-8 w-8 text-border" />
            <p className="mt-4 text-sm font-semibold text-text-secondary">No recent activity yet</p>
            <p className="mt-2 max-w-xs text-xs text-subtle">
              Feed activity will appear here once users start uploading, reviewing, or drafting.
            </p>
          </div>
        ) : (
          <div className="space-y-1">
            {rows.map((row) => (
              <ActivityFeedRow
                key={row.id}
                action={row.action}
                label={formatActivityLabel(row)}
                meta={formatActivityDetails(row)}
                time={formatRelativeActivityTime(row.occurred_at)}
                highlights={getActivityHighlights(row, 2)}
                compact
              />
            ))}
          </div>
        )}
      </SectionCard>

      {isModalOpen ? (
        <ActivityFeedModal isOpen={isModalOpen} onClose={() => setIsModalOpen(false)} />
      ) : null}
    </>
  );
};
