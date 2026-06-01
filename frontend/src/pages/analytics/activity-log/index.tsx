import React, { useEffect, useMemo, useState } from 'react';
import { FiActivity, FiChevronDown, FiChevronUp, FiSearch, FiX } from 'react-icons/fi';
import { SelectDropdown } from '@/components/common';
import { AnalyticsBodySkeleton } from '@/features/analytics/components/AnalyticsSkeleton';
import { AnalyticsTablePaginationFooter } from '@/features/analytics/components/AnalyticsTablePaginationFooter';
import { KpiSurface } from '@/features/analytics/components/KpiSurface';
import { SectionCard } from '@/features/analytics/components/SectionCard';
import { SortableHeader } from '@/features/analytics/components/SortableHeader';
import { useDashboardActivityActions } from '@/features/analytics/hooks/useDashboardActivityActions';
import { useDashboardActivityLog } from '@/features/analytics/hooks/useDashboardActivityLog';
import { useAnalyticsFiltersStore } from '@/features/analytics/stores/useAnalyticsFiltersStore';
import { AnalyticsLayout } from '@/features/analytics/components/shared';
import { formatRelativeActivityTime } from '@/features/analytics/utils/activityFeed.helpers';
import type { DashboardActivityLogEntityType } from '@/features/analytics/types/dashboard.types';
import {
  ACTIVITY_LOG_ENTITY_TYPE_OPTIONS,
  ACTIVITY_LOG_PAGE_SIZE_OPTIONS,
  ACTIVITY_LOG_STATUS_OPTIONS,
  formatActivityActionLabel,
  formatActivityActor,
  formatActivityDurationMs,
  formatActivityEntitySummary,
  getActivityMethodBadgeClass,
  getActivityStatusBadgeClass,
  resolveActivityApiPath,
  resolveActivityDurationMs,
  resolveActivityErrorInfo,
  resolveActivityHttpMethod,
  sortActivityLogRows,
  truncateActivityValue,
  type ActivityLogSortDirection,
  type ActivityLogSortKey,
} from '@/features/analytics/utils/activityLog.helpers';

export const AnalyticsActivityLogPage: React.FC = () => {
  const { rangePreset } = useAnalyticsFiltersStore();
  const [actionFilter, setActionFilter] = useState('');
  const [entityTypeFilter, setEntityTypeFilter] = useState<DashboardActivityLogEntityType | ''>('');

  const [searchInput, setSearchInput] = useState('');
  const [searchQuery, setSearchQuery] = useState('');

  const [showAdvancedFilters, setShowAdvancedFilters] = useState(false);

  const [actorIdInput, setActorIdInput] = useState('');
  const [entityIdInput, setEntityIdInput] = useState('');

  const [actorIdFilter, setActorIdFilter] = useState('');
  const [entityIdFilter, setEntityIdFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [sortKey, setSortKey] = useState<ActivityLogSortKey>('time');
  const [sortDir, setSortDir] = useState<ActivityLogSortDirection>('desc');

  const [pageSize, setPageSize] = useState<number>(10);
  const [page, setPage] = useState<number>(1);

  const trimmedSearchInput = useMemo(() => searchInput.trim(), [searchInput]);
  const trimmedActorIdInput = useMemo(() => actorIdInput.trim(), [actorIdInput]);
  const trimmedEntityIdInput = useMemo(() => entityIdInput.trim(), [entityIdInput]);

  useEffect(() => {
    const timeout = window.setTimeout(() => {
      setSearchQuery((current) => (current === trimmedSearchInput ? current : trimmedSearchInput));
    }, 300);

    return () => window.clearTimeout(timeout);
  }, [trimmedSearchInput]);

  useEffect(() => {
    const timeout = window.setTimeout(() => {
      setActorIdFilter((current) =>
        current === trimmedActorIdInput ? current : trimmedActorIdInput
      );
    }, 300);

    return () => window.clearTimeout(timeout);
  }, [trimmedActorIdInput]);

  useEffect(() => {
    const timeout = window.setTimeout(() => {
      setEntityIdFilter((current) =>
        current === trimmedEntityIdInput ? current : trimmedEntityIdInput
      );
    }, 300);

    return () => window.clearTimeout(timeout);
  }, [trimmedEntityIdInput]);

  useEffect(() => {
    setPage(1);
  }, [
    rangePreset,
    actionFilter,
    entityTypeFilter,
    searchQuery,
    actorIdFilter,
    entityIdFilter,
    statusFilter,
    pageSize,
  ]);

  const offset = (page - 1) * pageSize;
  const query = useMemo(
    () => ({
      limit: pageSize,
      offset,
      ...(actionFilter ? { action: actionFilter } : {}),
      ...(entityTypeFilter ? { entity_type: entityTypeFilter } : {}),
      ...(actorIdFilter ? { actor_id: actorIdFilter } : {}),
      ...(entityIdFilter ? { entity_id: entityIdFilter } : {}),
      ...(statusFilter ? { status: statusFilter } : {}),
      ...(searchQuery ? { search: searchQuery } : {}),
    }),
    [
      actionFilter,
      actorIdFilter,
      entityIdFilter,
      entityTypeFilter,
      offset,
      pageSize,
      searchQuery,
      statusFilter,
    ]
  );

  const { data, isLoading, isFetching, error } = useDashboardActivityLog(query);
  const { data: actionOptionsData } = useDashboardActivityActions(true);
  const actionOptions = useMemo(
    () => [{ label: 'All actions', value: '' }, ...(actionOptionsData ?? [])],
    [actionOptionsData]
  );

  const rows = useMemo(() => data?.items ?? [], [data?.items]);
  const sortedRows = useMemo(() => sortActivityLogRows(rows, sortKey, sortDir), [rows, sortDir, sortKey]);

  const totalItems = data?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(totalItems / pageSize));

  useEffect(() => {
    if (page > totalPages) {
      setPage(totalPages);
    }
  }, [page, totalPages]);

  const showingFrom = totalItems === 0 ? 0 : offset + 1;
  const showingTo = Math.min(offset + sortedRows.length, totalItems);
  const showTableSkeleton = isLoading || isFetching;
  const kpi = data?.kpi;
  const kpiTotalEvents = kpi?.total_events ?? totalItems;
  const kpiUniqueActors = kpi?.unique_actors ?? 0;
  const kpiErrorRate = kpi?.error_rate ?? 0;
  const kpiAvgDuration = formatActivityDurationMs(kpi?.avg_duration_ms ?? null) ?? '--';
  const hasActiveFilters = Boolean(
    actionFilter ||
      entityTypeFilter ||
      searchQuery ||
      actorIdInput.trim() ||
      entityIdInput.trim() ||
      statusFilter
  );

  const clearFilters = () => {
    setActionFilter('');
    setEntityTypeFilter('');
    setSearchInput('');
    setSearchQuery('');
    setActorIdInput('');
    setEntityIdInput('');
    setActorIdFilter('');
    setEntityIdFilter('');
    setStatusFilter('');
    setPage(1);
  };

  const handleHeaderSortToggle = (nextSortKey: ActivityLogSortKey) => {
    setSortDir((current) => {
      if (sortKey === nextSortKey) {
        return current === 'asc' ? 'desc' : 'asc';
      }
      return 'desc';
    });
    setSortKey(nextSortKey);
  };

  return (
    <AnalyticsLayout title="Activity Log">
      <section className="mb-8 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <KpiSurface
          label="Total Events"
          value={kpiTotalEvents.toLocaleString()}
          iconKey="totalCases"
          loading={isLoading && !data}
        />
        <KpiSurface
          label="Unique Actors"
          value={kpiUniqueActors.toLocaleString()}
          iconKey="totalUsers"
          loading={isLoading && !data}
        />
        <KpiSurface
          label="Error Rate"
          value={`${kpiErrorRate.toFixed(2)}%`}
          iconKey="pendingCases"
          valueClass={kpiErrorRate > 0 ? 'text-app-danger-text' : 'text-app-success-text'}
          loading={isLoading && !data}
        />
        <KpiSurface
          label="Avg Duration"
          value={kpiAvgDuration}
          iconKey="motionsDrafted"
          loading={isLoading && !data}
        />
      </section>

      <SectionCard
        className="mb-8"
        headerClassName="items-start"
        title={
          <div className="pt-3 flex items-center gap-2">
            <FiActivity className="h-4 w-4 text-app-accent" />
            <span>Activities</span>
          </div>
        }
        action={
          <div className="ml-auto flex max-w-[1100px] flex-col items-start gap-2">
            <div className="flex flex-wrap items-center justify-start gap-2">
              <div className="min-w-[176px]">
                <SelectDropdown
                  value={actionFilter}
                  onChange={setActionFilter}
                  options={actionOptions}
                  className="w-full [&>button]:h-[40px] [&>button]:py-0"
                />
              </div>

              <div className="min-w-[176px]">
                <SelectDropdown
                  value={entityTypeFilter}
                  onChange={(value) =>
                    setEntityTypeFilter(value as DashboardActivityLogEntityType | '')
                  }
                  options={ACTIVITY_LOG_ENTITY_TYPE_OPTIONS}
                  className="w-full [&>button]:h-[40px] [&>button]:py-0"
                />
              </div>

              <label className="relative block min-w-[320px]">
                <FiSearch className="pointer-events-none absolute left-4 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-subtle" />
                <input
                  type="text"
                  value={searchInput}
                  onChange={(event) => setSearchInput(event.target.value)}
                  placeholder="Search actor, detail, entity, action..."
                  className="h-[40px] w-full rounded-xl border-0 bg-surface-muted pl-10 pr-10 text-sm text-text-secondary outline-none transition focus:ring-2 focus:ring-option-selected-ring placeholder:text-subtle"
                />
                {searchInput.length ? (
                  <button
                    type="button"
                    onClick={() => {
                      setSearchInput('');
                      setSearchQuery('');
                      setPage(1);
                    }}
                    aria-label="Clear search"
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-subtle transition hover:text-text-secondary"
                  >
                    <FiX className="h-3.5 w-3.5" />
                  </button>
                ) : null}
              </label>

              <button
                type="button"
                onClick={() => setShowAdvancedFilters((current) => !current)}
                className="inline-flex h-[40px] items-center gap-1 rounded-xl border border-border/80 bg-surface-muted px-3 text-sm font-semibold text-text transition hover:bg-surface"
              >
                More filters
                {showAdvancedFilters ? (
                  <FiChevronUp className="h-4 w-4" />
                ) : (
                  <FiChevronDown className="h-4 w-4" />
                )}
              </button>
            </div>

            {showAdvancedFilters ? (
              <div className="grid w-full gap-2 rounded-xl border border-border bg-surface p-2.5 sm:grid-cols-3">
                <label className="relative block">
                  <FiSearch className="pointer-events-none absolute left-4 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-subtle" />
                  <input
                    type="text"
                    value={actorIdInput}
                    onChange={(event) => setActorIdInput(event.target.value)}
                    placeholder="Filter actor ID..."
                    className="h-[40px] w-full rounded-xl border border-border/70 bg-surface-muted pl-10 pr-10 text-sm text-text-secondary outline-none transition focus:ring-2 focus:ring-option-selected-ring placeholder:text-subtle"
                  />
                  {actorIdInput.length ? (
                    <button
                      type="button"
                      onClick={() => {
                        setActorIdInput('');
                        setActorIdFilter('');
                        setPage(1);
                      }}
                      aria-label="Clear actor ID"
                      className="absolute right-3 top-1/2 -translate-y-1/2 text-subtle transition hover:text-text-secondary"
                    >
                      <FiX className="h-3.5 w-3.5" />
                    </button>
                  ) : null}
                </label>

                <label className="relative block">
                  <FiSearch className="pointer-events-none absolute left-4 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-subtle" />
                  <input
                    type="text"
                    value={entityIdInput}
                    onChange={(event) => setEntityIdInput(event.target.value)}
                    placeholder="Filter entity ID (advanced)..."
                    className="h-[40px] w-full rounded-xl border border-border/70 bg-surface-muted pl-10 pr-10 text-sm text-text-secondary outline-none transition focus:ring-2 focus:ring-option-selected-ring placeholder:text-subtle"
                  />
                  {entityIdInput.length ? (
                    <button
                      type="button"
                      onClick={() => {
                        setEntityIdInput('');
                        setEntityIdFilter('');
                        setPage(1);
                      }}
                      aria-label="Clear entity ID"
                      className="absolute right-3 top-1/2 -translate-y-1/2 text-subtle transition hover:text-text-secondary"
                    >
                      <FiX className="h-3.5 w-3.5" />
                    </button>
                  ) : null}
                </label>

                <div className="min-w-0">
                  <SelectDropdown
                    value={statusFilter}
                    onChange={setStatusFilter}
                    options={ACTIVITY_LOG_STATUS_OPTIONS}
                    className="w-full [&>button]:h-[40px] [&>button]:py-0"
                  />
                </div>
              </div>
            ) : null}
          </div>
        }
      >
        {error ? (
          <div className="rounded-2xl border border-app-danger-text/30 bg-app-danger-soft px-4 py-3 text-sm text-app-danger-text">
            Failed to load activity log: {error.message}
          </div>
        ) : (
          <>
            <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
              {showTableSkeleton ? (
                <AnalyticsBodySkeleton className="h-4 max-w-44" />
              ) : (
                <p className="text-xs text-muted">
                  Showing {showingFrom}–{showingTo} of {totalItems.toLocaleString()} activities
                </p>
              )}
              <div className="flex items-center gap-3">
                {hasActiveFilters ? (
                  <button
                    type="button"
                    onClick={clearFilters}
                    className="text-xs font-medium text-app-accent-text transition hover:underline"
                  >
                    Clear filters
                  </button>
                ) : null}
              </div>
            </div>

            <div className="overflow-x-auto rounded-2xl border border-border/70">
              <table className="w-full min-w-[1160px] table-fixed border-collapse">
                <thead className="bg-surface-muted/75">
                  <tr>
                    <th className="w-[11%] px-4 py-3 text-left whitespace-nowrap">
                      <SortableHeader
                        label="Time"
                        sortKey="time"
                        activeSortKey={sortKey}
                        sortDir={sortDir}
                        onToggle={handleHeaderSortToggle}
                      />
                    </th>
                    <th className="w-[16%] px-4 py-3 text-left whitespace-nowrap">
                      <SortableHeader
                        label="Actor"
                        sortKey="actor"
                        activeSortKey={sortKey}
                        sortDir={sortDir}
                        onToggle={handleHeaderSortToggle}
                      />
                    </th>
                    <th className="w-[13%] px-4 py-3 text-left whitespace-nowrap">
                      <SortableHeader
                        label="Action"
                        sortKey="action"
                        activeSortKey={sortKey}
                        sortDir={sortDir}
                        onToggle={handleHeaderSortToggle}
                      />
                    </th>
                    <th className="w-[33%] px-4 py-3 text-left whitespace-nowrap">
                      <span className="inline-flex whitespace-nowrap text-[11px] font-semibold uppercase tracking-[0.12em] text-muted">
                        Detail
                      </span>
                    </th>
                    <th className="w-[9%] px-4 py-3 text-left whitespace-nowrap">
                      <SortableHeader
                        label="Status"
                        sortKey="status"
                        activeSortKey={sortKey}
                        sortDir={sortDir}
                        onToggle={handleHeaderSortToggle}
                      />
                    </th>
                    <th className="w-[9%] px-4 py-3 text-left whitespace-nowrap">
                      <SortableHeader
                        label="Duration"
                        sortKey="duration"
                        activeSortKey={sortKey}
                        sortDir={sortDir}
                        onToggle={handleHeaderSortToggle}
                      />
                    </th>
                    <th className="w-[9%] px-4 py-3 text-left whitespace-nowrap">
                      <span className="inline-flex whitespace-nowrap text-[11px] font-semibold uppercase tracking-[0.12em] text-muted">
                        Error
                      </span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {showTableSkeleton ? (
                    Array.from({ length: 10 }).map((_, index) => (
                      <tr
                        key={`activity-log-skeleton-${index}`}
                        className="border-t border-border/70"
                      >
                        <td className="px-4 py-3">
                          <AnalyticsBodySkeleton className="h-5 w-20" />
                        </td>
                        <td className="px-4 py-3">
                          <AnalyticsBodySkeleton className="h-5 w-32" />
                        </td>
                        <td className="px-4 py-3">
                          <AnalyticsBodySkeleton className="h-5 w-24" />
                        </td>
                        <td className="px-4 py-3">
                          <AnalyticsBodySkeleton className="h-5 w-full" />
                        </td>
                        <td className="px-4 py-3">
                          <AnalyticsBodySkeleton className="h-5 w-16" />
                        </td>
                        <td className="px-4 py-3">
                          <AnalyticsBodySkeleton className="h-5 w-16" />
                        </td>
                        <td className="px-4 py-3">
                          <AnalyticsBodySkeleton className="h-5 w-24" />
                        </td>
                      </tr>
                    ))
                  ) : sortedRows.length ? (
                    sortedRows.map((entry) => {
                      const resolvedDuration = formatActivityDurationMs(resolveActivityDurationMs(entry));
                      const errorInfo = resolveActivityErrorInfo(entry);
                      const httpMethod = resolveActivityHttpMethod(entry);
                      const apiPath = resolveActivityApiPath(entry);

                      return (
                        <tr
                          key={entry.id}
                          className="border-t border-border/70 transition-colors hover:bg-activity-row-hover"
                        >
                          <td className="px-4 py-3 text-xs text-muted whitespace-nowrap">
                            {formatRelativeActivityTime(entry.occurred_at)}
                          </td>
                          <td className="px-4 py-3">
                            <p
                              className="truncate text-xs text-text-secondary"
                              title={formatActivityActor(entry)}
                            >
                              {truncateActivityValue(formatActivityActor(entry), 28)}
                            </p>
                          </td>
                          <td className="px-4 py-3">
                            <span className="whitespace-nowrap rounded-full border border-border bg-app-accent-soft px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-app-accent-text">
                              {truncateActivityValue(entry.label || formatActivityActionLabel(entry.action), 20)}
                            </span>
                          </td>
                          <td className="px-4 py-3">
                            <div className="flex min-w-0 items-center gap-2">
                              <span
                                className={`shrink-0 rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${getActivityMethodBadgeClass(
                                  httpMethod
                                )}`}
                              >
                                {httpMethod ?? 'N/A'}
                              </span>
                              <span
                                className="min-w-0 flex-1 truncate text-xs text-text-secondary"
                                title={
                                  apiPath ?? entry.detail?.trim() ?? formatActivityEntitySummary(entry)
                                }
                              >
                                {apiPath
                                  ? truncateActivityValue(apiPath, 96)
                                  : entry.detail?.trim()
                                    ? truncateActivityValue(entry.detail.trim(), 96)
                                    : truncateActivityValue(formatActivityEntitySummary(entry), 96)}
                              </span>
                            </div>
                          </td>
                          <td className="px-4 py-3">
                            {entry.status ? (
                              <span
                                className={`rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${getActivityStatusBadgeClass(
                                  entry.status
                                )}`}
                              >
                                {truncateActivityValue(entry.status, 12)}
                              </span>
                            ) : (
                              <span className="text-xs text-subtle">--</span>
                            )}
                          </td>
                          <td className="px-4 py-3 text-xs whitespace-nowrap">
                            {resolvedDuration ? (
                              <span className="font-medium text-text-secondary">
                                {resolvedDuration}
                              </span>
                            ) : (
                              <span className="text-subtle">Pending</span>
                            )}
                          </td>
                          <td className="px-4 py-3">
                            {errorInfo.code || errorInfo.message ? (
                              <div className="flex flex-col gap-0.5">
                                {errorInfo.code ? (
                                  <span
                                    className="truncate text-[10px] font-semibold uppercase tracking-wide text-app-danger-text"
                                    title={errorInfo.code}
                                  >
                                    {truncateActivityValue(errorInfo.code, 20)}
                                  </span>
                                ) : null}
                                {errorInfo.message ? (
                                  <span
                                    className="truncate text-[10px] text-muted"
                                    title={errorInfo.message}
                                  >
                                    {truncateActivityValue(errorInfo.message, 24)}
                                  </span>
                                ) : null}
                              </div>
                            ) : (
                              <span className="text-xs text-subtle">Pending</span>
                            )}
                          </td>
                        </tr>
                      );
                    })
                  ) : (
                    <tr>
                      <td colSpan={7} className="px-4 py-8 text-center text-sm text-muted">
                        No activity found for this filter set.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>

            <AnalyticsTablePaginationFooter
              page={page}
              totalPages={totalPages}
              pageSize={pageSize}
              pageSizeOptions={ACTIVITY_LOG_PAGE_SIZE_OPTIONS}
              onPageChange={setPage}
              onPageSizeChange={setPageSize}
              className="mt-4"
              keyPrefix="activity-log-pagination"
            />
          </>
        )}
      </SectionCard>
    </AnalyticsLayout>
  );
};
