import React, { useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import {
  FiArrowLeft,
  FiClock,
  FiExternalLink,
  FiFileText,
  FiMapPin,
  FiPieChart,
} from 'react-icons/fi';
import { SelectDropdown } from '@/components/common';
import { SidebarLayout } from '@/components/layout/SidebarLayout';
import { AnalyticsBodySkeleton } from '@/features/analytics/components/AnalyticsSkeleton';
import { AnalyticsTablePaginationFooter } from '@/features/analytics/components/AnalyticsTablePaginationFooter';
import { KpiSurface } from '@/features/analytics/components/KpiSurface';
import { SectionCard } from '@/features/analytics/components/SectionCard';
import { SortableHeader } from '@/features/analytics/components/SortableHeader';
import { useDashboardAnalyticsMotionSessionDetail } from '@/features/analytics/hooks/useDashboardAnalyticsMotionSessionDetail';
import type {
  DashboardMotionSessionByTypeItem,
  DashboardMotionsAnalyticsSortBy,
} from '@/features/analytics/types/dashboard.types';
import {
  getMotionSessionCategoryBadgeClass,
  getMotionSessionCompletionRatio,
  getMotionSessionCosBadgeClass,
  getMotionSessionStatusBadgeClass,
  MOTION_SESSION_DETAIL_CATEGORY_OPTIONS,
  MOTION_SESSION_DETAIL_PAGE_SIZE_OPTIONS,
  MOTION_SESSION_DETAIL_STATUS_OPTIONS,
  formatMotionSessionCosType,
  formatMotionSessionDateTime,
  formatMotionSessionDuration,
  formatMotionSessionLabel,
} from '@/features/analytics/utils/motionSessionDetail.helpers';
import { formatDistrictLabel } from '@/features/analytics/utils/districtLabels';
import { formatAnalyticsNumber } from '@/features/analytics/utils/dashboard.mappers';

interface ByTypeBlockProps {
  title: string;
  items: DashboardMotionSessionByTypeItem[];
  barClassName: string;
  emptyLabel: string;
}

const ByTypeBlock: React.FC<ByTypeBlockProps> = ({ title, items, barClassName, emptyLabel }) => (
  <div className="rounded-xl border border-border/70 bg-surface-muted/40 p-3">
    <div className="mb-3 flex items-center justify-between gap-2">
      <h4 className="text-xs font-semibold uppercase tracking-[0.12em] text-subtle">{title}</h4>
      <span className="text-[10px] font-medium uppercase tracking-[0.1em] text-subtle">
        Completed / Total Attempts
      </span>
    </div>
    {items.length ? (
      <div className="space-y-2.5">
        {items.map((item) => {
          const ratio = getMotionSessionCompletionRatio(item.completed, item.total_attempted);

          return (
            <div key={item.motion_type} className="rounded-lg border border-border/60 bg-surface px-2.5 py-2">
              <div className="mb-1.5 flex items-center justify-between gap-2">
                <p className="truncate text-xs font-medium text-text-secondary">{item.display_name}</p>
                <p className="shrink-0 text-[11px] text-muted">
                  {formatAnalyticsNumber(item.completed)} / {formatAnalyticsNumber(item.total_attempted)}
                  <span className="ml-1 text-subtle">({Math.round(ratio)}%)</span>
                </p>
              </div>
              <div className="h-1.5 rounded-full bg-surface-muted">
                <div className={`h-full rounded-full ${barClassName}`} style={{ width: `${ratio}%` }} />
              </div>
            </div>
          );
        })}
      </div>
    ) : (
      <p className="text-xs text-subtle">{emptyLabel}</p>
    )}
  </div>
);

export const AnalyticsMotionSessionDetailPage: React.FC = () => {
  const navigate = useNavigate();
  const { sessionId } = useParams<{ sessionId: string }>();
  const [searchInput, setSearchInput] = useState('');
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [categoryFilter, setCategoryFilter] = useState('');
  const [pageSize, setPageSize] = useState<number>(10);
  const [page, setPage] = useState<number>(1);
  const [sortKey, setSortKey] = useState<DashboardMotionsAnalyticsSortBy>('created_at');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc');

  const detailQuery = useMemo(
    () => ({
      page,
      page_size: pageSize,
      sort_by: sortKey,
      sort_dir: sortDir,
      ...(statusFilter ? { status: statusFilter as 'pending' | 'completed' | 'failed' | 'cancelled' } : {}),
      ...(categoryFilter ? { category: categoryFilter as 'motion' | 'order' } : {}),
      ...(searchQuery ? { search: searchQuery } : {}),
    }),
    [categoryFilter, page, pageSize, searchQuery, sortDir, sortKey, statusFilter]
  );

  const {
    data: detail,
    isLoading,
    error,
  } = useDashboardAnalyticsMotionSessionDetail(sessionId ?? null, detailQuery, Boolean(sessionId));

  useEffect(() => {
    const timeout = window.setTimeout(() => {
      setSearchQuery((current) => (current === searchInput.trim() ? current : searchInput.trim()));
    }, 300);

    return () => window.clearTimeout(timeout);
  }, [searchInput]);

  useEffect(() => {
    setPage(1);
  }, [statusFilter, categoryFilter, searchQuery, pageSize, sortKey, sortDir]);

  useEffect(() => {
    setSearchInput('');
    setSearchQuery('');
    setStatusFilter('');
    setCategoryFilter('');
    setPageSize(10);
    setPage(1);
    setSortKey('created_at');
    setSortDir('desc');
  }, [sessionId]);

  const attemptedCount = detail?.kpis.total_motions_and_orders ?? 0;
  const completedCount = detail?.kpis.completed ?? 0;
  const completedRate = attemptedCount ? (completedCount / attemptedCount) * 100 : 0;
  const completedMotionCount = detail
    ? detail.by_type.motions.reduce((sum, item) => sum + item.completed, 0)
    : 0;
  const cosCoverage = completedMotionCount
    ? ((detail?.kpis.total_cos_generated ?? 0) / completedMotionCount) * 100
    : 0;
  const pagedMotions = detail?.motions ?? [];
  const totalItems = detail?.pagination.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(totalItems / pageSize));
  const currentPage = detail?.pagination.page ?? page;
  const showingFrom = totalItems === 0 ? 0 : (currentPage - 1) * pageSize + 1;
  const showingTo = Math.min((currentPage - 1) * pageSize + pagedMotions.length, totalItems);
  const hasActiveFilters = Boolean(searchInput.trim() || statusFilter || categoryFilter);

  const handleHeaderSortToggle = (nextSortKey: DashboardMotionsAnalyticsSortBy) => {
    setSortDir((current) => {
      if (sortKey === nextSortKey) {
        return current === 'asc' ? 'desc' : 'asc';
      }
      return 'desc';
    });
    setSortKey(nextSortKey);
  };

  useEffect(() => {
    if (page > totalPages) {
      setPage(totalPages);
    }
  }, [page, totalPages]);

  if (!sessionId) {
    return (
      <SidebarLayout sidebarVariant="analytics" className="bg-page" contentClassName="overflow-y-auto">
        <div className="mx-auto w-full max-w-[1600px] px-6 py-8 pb-16 xl:px-8">
          <div className="rounded-2xl border border-app-danger-text/30 bg-app-danger-soft px-4 py-3 text-sm text-app-danger-text">
            Missing motion session id.
          </div>
        </div>
      </SidebarLayout>
    );
  }

  return (
    <SidebarLayout sidebarVariant="analytics" className="bg-page" contentClassName="overflow-y-auto">
      <div className="mx-auto w-full max-w-[1600px] px-6 py-8 pb-16 xl:px-8">
        <div className="mb-5 flex items-center gap-2 text-xs text-muted">
          <button
            type="button"
            onClick={() => navigate('/analytics/motions')}
            className="inline-flex items-center gap-1 rounded-lg px-2 py-1 font-medium text-text-secondary transition hover:bg-surface-muted"
          >
            <FiArrowLeft className="h-3.5 w-3.5" />
            Back to Motions
          </button>
        </div>

        {error ? (
          <div className="rounded-2xl border border-app-danger-text/30 bg-app-danger-soft px-4 py-3 text-sm text-app-danger-text">
            Failed to load motion session detail: {error.message}
          </div>
        ) : isLoading || !detail ? (
          <AnalyticsBodySkeleton className="h-[420px]" />
        ) : (
          <>
            <SectionCard
              className="mb-6"
              title={
                <div className="min-w-0">
                  <h1 className="truncate text-2xl font-semibold text-text">
                    {detail.case_number || detail.session_id}
                  </h1>
                  <p className="mt-1 truncate text-sm text-muted">
                    {detail.debtor_name || 'Unknown debtor'}
                  </p>
                </div>
              }
              action={
                <div className="flex flex-wrap items-center gap-2">
                  {detail.district ? (
                    <span className="inline-flex items-center gap-1.5 rounded-full bg-surface-muted px-2.5 py-1 text-xs font-semibold text-muted">
                      <FiMapPin className="h-3 w-3" />
                      {formatDistrictLabel(detail.district)}
                    </span>
                  ) : null}
                  <span className="rounded-full bg-surface-muted px-2.5 py-1 text-xs font-semibold text-muted">
                    Session {detail.session_id}
                  </span>
                  <button
                    type="button"
                    onClick={() =>
                      window.open(
                        `/dashboard/${encodeURIComponent(detail.session_id)}`,
                        '_blank',
                        'noopener,noreferrer'
                      )
                    }
                    className="ml-2 inline-flex items-center gap-2 rounded-xl border border-border px-3 py-2 text-xs font-semibold text-text-secondary transition hover:bg-surface-muted"
                  >
                    <FiExternalLink className="h-3.5 w-3.5" />
                    Open In Dashboard
                  </button>
                </div>
              }
            >
              <div className="grid gap-3 sm:grid-cols-3 xl:grid-cols-6">
                <KpiSurface
                  label="Total Drafts"
                  value={formatAnalyticsNumber(attemptedCount)}
                  iconKey="motionsDrafted"
                />
                <KpiSurface
                  label="Motions"
                  value={formatAnalyticsNumber(detail.kpis.total_motions)}
                  iconKey="motionsDrafted"
                />
                <KpiSurface
                  label="Orders"
                  value={formatAnalyticsNumber(detail.kpis.total_orders)}
                  iconKey="totalCases"
                />
                <KpiSurface
                  label="Completed"
                  value={formatAnalyticsNumber(detail.kpis.completed)}
                  iconKey="activeCases"
                  valueClass="text-app-success-text"
                />
                <KpiSurface
                  label="Failed"
                  value={formatAnalyticsNumber(detail.kpis.failed)}
                  iconKey="pendingCases"
                  valueClass="text-app-danger-text"
                />
                <KpiSurface
                  label="Cancelled"
                  value={formatAnalyticsNumber(detail.kpis.cancelled)}
                  iconKey="pendingCases"
                  valueClass="text-muted"
                />
              </div>
            </SectionCard>

            <div className="mb-6 grid items-start gap-6 xl:grid-cols-[1.2fr_0.8fr]">
              <SectionCard
                title={
                  <div className="flex items-center gap-2">
                    <FiPieChart className="h-4 w-4 text-app-accent" />
                    <span>Type Breakdown</span>
                  </div>
                }
              >
                <div className="grid gap-3 md:grid-cols-2">
                  <ByTypeBlock
                    title="Motions"
                    items={detail.by_type.motions}
                    barClassName="bg-app-accent"
                    emptyLabel="No motion types drafted in this session."
                  />
                  <ByTypeBlock
                    title="Orders"
                    items={detail.by_type.orders}
                    barClassName="bg-app-warning-text"
                    emptyLabel="No order types drafted in this session."
                  />
                </div>
                <p className="mt-3 text-[11px] text-subtle">
                  Each row shows completed / total attempts for this session.
                </p>
              </SectionCard>

              <SectionCard
                className="self-start xl:sticky xl:top-6"
                title={
                  <div className="flex items-center gap-2">
                    <FiClock className="h-4 w-4 text-app-accent" />
                    <span>COS & Processing</span>
                  </div>
                }
              >
                <div className="flex flex-col gap-3">
                  <div className="rounded-xl border border-border bg-surface-muted/40 px-3 py-2.5">
                    <p className="text-[10px] uppercase tracking-[0.12em] text-subtle">Avg Processing</p>
                    <p className="mt-1 text-lg font-semibold text-text">
                      {formatMotionSessionDuration(detail.kpis.avg_processing_seconds)}
                    </p>
                    <p className="mt-1 text-[11px] text-subtle">
                      {formatAnalyticsNumber(completedCount)} / {formatAnalyticsNumber(attemptedCount)} completed (
                      {completedRate.toFixed(1)}%)
                    </p>
                  </div>

                  <div className="rounded-xl border border-border bg-surface-muted/40 px-3 py-2.5">
                    <p className="text-[10px] uppercase tracking-[0.12em] text-subtle">Total COS Generated</p>
                    <p className="mt-1 text-lg font-semibold text-text">
                      {formatAnalyticsNumber(detail.kpis.total_cos_generated)}
                    </p>
                    <div className="mt-2 grid gap-2 sm:grid-cols-2">
                      <div className="rounded-lg border border-border/70 bg-surface px-2.5 py-2">
                        <p className="text-[10px] uppercase tracking-[0.1em] text-subtle">With Notice</p>
                        <p className="mt-1 text-sm font-semibold text-app-success-text">
                          {formatAnalyticsNumber(detail.kpis.cos_with_notice_of_hearing)}
                        </p>
                      </div>
                      <div className="rounded-lg border border-border/70 bg-surface px-2.5 py-2">
                        <p className="text-[10px] uppercase tracking-[0.1em] text-subtle">Without Notice</p>
                        <p className="mt-1 text-sm font-semibold text-app-warning-text">
                          {formatAnalyticsNumber(detail.kpis.cos_without_notice_of_hearing)}
                        </p>
                      </div>
                    </div>
                  </div>

                  <div className="rounded-xl border border-border bg-surface-muted/40 px-3 py-2.5">
                    <p className="text-[10px] uppercase tracking-[0.12em] text-subtle">Outcome Snapshot</p>
                    <div className="mt-2 grid gap-2 sm:grid-cols-3">
                      <div className="rounded-lg border border-border/70 bg-surface px-2.5 py-2">
                        <p className="text-[10px] uppercase tracking-[0.1em] text-subtle">Completed</p>
                        <p className="mt-1 text-sm font-semibold text-app-success-text">
                          {formatAnalyticsNumber(detail.kpis.completed)}
                        </p>
                      </div>
                      <div className="rounded-lg border border-border/70 bg-surface px-2.5 py-2">
                        <p className="text-[10px] uppercase tracking-[0.1em] text-subtle">Failed</p>
                        <p className="mt-1 text-sm font-semibold text-app-danger-text">
                          {formatAnalyticsNumber(detail.kpis.failed)}
                        </p>
                      </div>
                      <div className="rounded-lg border border-border/70 bg-surface px-2.5 py-2">
                        <p className="text-[10px] uppercase tracking-[0.1em] text-subtle">Cancelled</p>
                        <p className="mt-1 text-sm font-semibold text-muted">
                          {formatAnalyticsNumber(detail.kpis.cancelled)}
                        </p>
                      </div>
                    </div>
                    <div className="mt-2">
                      <p className="text-[10px] uppercase tracking-[0.1em] text-subtle">
                        COS Coverage (Completed Motions)
                      </p>
                      <div className="mt-1.5 h-1.5 rounded-full bg-surface-muted">
                        <div
                          className="h-full rounded-full bg-app-accent"
                          style={{ width: `${Math.max(0, Math.min(100, cosCoverage))}%` }}
                        />
                      </div>
                      <p className="mt-1 text-[11px] text-subtle">{cosCoverage.toFixed(1)}%</p>
                    </div>
                  </div>
                </div>
              </SectionCard>
            </div>

            <SectionCard
              headerClassName="items-start gap-3"
              title={
                <div className="flex items-center gap-2">
                  <FiFileText className="h-4 w-4 text-app-accent" />
                  <span>Session Motions & Orders</span>
                </div>
              }
              action={
                <div className="ml-auto flex flex-wrap items-center justify-end gap-2">
                  <label className="relative block min-w-[320px]">
                    <input
                      type="text"
                      value={searchInput}
                      onChange={(event) => setSearchInput(event.target.value)}
                      placeholder="Search case number..."
                      className="h-[40px] w-full rounded-xl border-0 bg-surface-muted pl-3 pr-9 text-sm text-text-secondary outline-none transition focus:ring-2 focus:ring-option-selected-ring placeholder:text-subtle"
                    />
                  </label>

                  <div className="min-w-[160px]">
                    <SelectDropdown
                      value={statusFilter}
                      onChange={setStatusFilter}
                      options={MOTION_SESSION_DETAIL_STATUS_OPTIONS}
                      className="w-full [&>button]:h-[40px] [&>button]:py-0"
                    />
                  </div>

                  <div className="min-w-[160px]">
                    <SelectDropdown
                      value={categoryFilter}
                      onChange={setCategoryFilter}
                      options={MOTION_SESSION_DETAIL_CATEGORY_OPTIONS}
                      className="w-full [&>button]:h-[40px] [&>button]:py-0"
                    />
                  </div>
                </div>
              }
            >
              <div className="mb-3 flex items-center justify-between gap-2">
                <p className="text-xs text-muted">
                  Showing {showingFrom}–{showingTo} of {formatAnalyticsNumber(totalItems)} items
                </p>
                {hasActiveFilters ? (
                  <button
                    type="button"
                    onClick={() => {
                      setSearchInput('');
                      setSearchQuery('');
                      setStatusFilter('');
                      setCategoryFilter('');
                      setPage(1);
                    }}
                    className="text-xs font-medium text-app-accent-text transition hover:underline"
                  >
                    Clear filters
                  </button>
                ) : null}
              </div>

              <div className="overflow-hidden rounded-xl border border-border/70">
                <div className="overflow-x-auto">
                  <table className="w-full min-w-[1160px] table-fixed border-collapse">
                    <thead className="bg-surface-muted/75">
                      <tr>
                        <th className="w-[22%] whitespace-nowrap px-4 py-3 text-left text-[11px] font-semibold uppercase tracking-[0.12em] text-muted">
                          <SortableHeader
                            label="Type"
                            sortKey="motion_type"
                            activeSortKey={sortKey}
                            sortDir={sortDir}
                            onToggle={handleHeaderSortToggle}
                          />
                        </th>
                        <th className="w-[10%] whitespace-nowrap px-4 py-3 text-left text-[11px] font-semibold uppercase tracking-[0.12em] text-muted">
                          Category
                        </th>
                        <th className="w-[12%] whitespace-nowrap px-4 py-3 text-left text-[11px] font-semibold uppercase tracking-[0.12em] text-muted">
                          <SortableHeader
                            label="Status"
                            sortKey="status"
                            activeSortKey={sortKey}
                            sortDir={sortDir}
                            onToggle={handleHeaderSortToggle}
                          />
                        </th>
                        <th className="w-[14%] whitespace-nowrap px-4 py-3 text-left text-[11px] font-semibold uppercase tracking-[0.12em] text-muted">
                          COS Type
                        </th>
                        <th className="w-[16%] whitespace-nowrap px-4 py-3 text-left text-[11px] font-semibold uppercase tracking-[0.12em] text-muted">
                          <SortableHeader
                            label="Created"
                            sortKey="created_at"
                            activeSortKey={sortKey}
                            sortDir={sortDir}
                            onToggle={handleHeaderSortToggle}
                          />
                        </th>
                        <th className="w-[16%] whitespace-nowrap px-4 py-3 text-left text-[11px] font-semibold uppercase tracking-[0.12em] text-muted">
                          Completed
                        </th>
                        <th className="w-[10%] whitespace-nowrap px-4 py-3 text-left text-[11px] font-semibold uppercase tracking-[0.12em] text-muted">
                          <SortableHeader
                            label="Processing"
                            sortKey="processing_seconds"
                            activeSortKey={sortKey}
                            sortDir={sortDir}
                            onToggle={handleHeaderSortToggle}
                          />
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {pagedMotions.length ? (
                        pagedMotions.map((motion) => (
                          <tr key={motion.task_id} className="border-t border-border/70">
                            <td className="px-4 py-3 text-xs text-text-secondary">
                              <p className="truncate" title={motion.display_name || motion.motion_type}>
                                {motion.display_name || formatMotionSessionLabel(motion.motion_type)}
                              </p>
                            </td>
                            <td className="px-4 py-3">
                              <span
                                className={`inline-flex whitespace-nowrap rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${getMotionSessionCategoryBadgeClass(
                                  motion.category
                                )}`}
                              >
                                {formatMotionSessionLabel(motion.category)}
                              </span>
                            </td>
                            <td className="px-4 py-3">
                              <span
                                className={`inline-flex whitespace-nowrap rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${getMotionSessionStatusBadgeClass(
                                  motion.status
                                )}`}
                              >
                                {formatMotionSessionLabel(motion.status)}
                              </span>
                            </td>
                            <td className="px-4 py-3">
                              <span
                                className={`inline-flex whitespace-nowrap rounded-full px-2 py-0.5 text-[10px] font-semibold ${getMotionSessionCosBadgeClass(
                                  motion.cos_type
                                )}`}
                              >
                                {formatMotionSessionCosType(motion.cos_type)}
                              </span>
                            </td>
                            <td className="px-4 py-3 text-xs text-muted whitespace-nowrap">
                              {formatMotionSessionDateTime(motion.created_at)}
                            </td>
                            <td className="px-4 py-3 text-xs text-muted whitespace-nowrap">
                              {formatMotionSessionDateTime(motion.completed_at)}
                            </td>
                            <td className="px-4 py-3 text-xs font-medium text-text-secondary whitespace-nowrap">
                              {formatMotionSessionDuration(motion.processing_seconds)}
                            </td>
                          </tr>
                        ))
                      ) : (
                        <tr>
                          <td colSpan={7} className="px-4 py-8 text-center text-sm text-muted">
                            No motions found for this filter set.
                          </td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>

                <AnalyticsTablePaginationFooter
                  page={currentPage}
                  totalPages={totalPages}
                  pageSize={pageSize}
                  pageSizeOptions={MOTION_SESSION_DETAIL_PAGE_SIZE_OPTIONS}
                  onPageChange={setPage}
                  onPageSizeChange={setPageSize}
                  className="border-t border-border/70 bg-surface"
                  keyPrefix="session-motions-pagination"
                />
              </div>
            </SectionCard>
          </>
        )}
      </div>
    </SidebarLayout>
  );
};
