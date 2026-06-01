import React, { useEffect, useState } from 'react';
import { FiActivity, FiSearch, FiX } from 'react-icons/fi';
import { SelectDropdown } from '@/components/common';
import { AnalyticsTablePaginationFooter } from '@/features/analytics/components/AnalyticsTablePaginationFooter';
import { SectionCard } from '@/features/analytics/components/SectionCard';
import { SortableHeader } from '@/features/analytics/components/SortableHeader';
import { useUserDetailPageContext } from './UserDetailPageContext';
import type {
  UserDetailActivityAction,
  UserDetailActivityStatus,
  UserDetailActivityStatusFilter,
  UserDetailActivitySortKey,
  UserDetailSortDirection,
} from '@/features/analytics/types';
import { formatRelativeActivityTime } from '@/features/analytics/utils/activityFeed.helpers';
import { formatAnalyticsNumber } from '@/features/analytics/utils/dashboard.mappers';
import {
  ACTIVITY_ACTION_OPTIONS,
  ACTIVITY_STATUS_OPTIONS,
  DETAIL_PAGE_SIZE_OPTIONS,
  formatDurationMs,
  getStatusBadgeClass,
  toTitleCase,
} from '@/features/analytics/utils/userDetail.helpers';

export const UserDetailActivityCard: React.FC = () => {
  const { detail, activityQuery: query, setActivityQuery } = useUserDetailPageContext();
  const [searchInput, setSearchInput] = useState(query.search);

  useEffect(() => {
    setSearchInput(query.search);
  }, [query.search]);

  useEffect(() => {
    const timeout = window.setTimeout(() => {
      const trimmed = searchInput.trim();
      if (trimmed !== query.search) {
        setActivityQuery((previous) => ({ ...previous, page: 1, search: trimmed }));
      }
    }, 300);

    return () => window.clearTimeout(timeout);
  }, [searchInput, query.search, setActivityQuery]);

  const setActionFilter = (action: UserDetailActivityAction | '') => {
    setActivityQuery((previous) => ({ ...previous, page: 1, action }));
  };

  const setStatusFilter = (status: UserDetailActivityStatusFilter | '') => {
    setActivityQuery((previous) => ({ ...previous, page: 1, status }));
  };

  const setPage = (page: number) => {
    setActivityQuery((previous) => ({ ...previous, page }));
  };

  const setPageSize = (pageSize: number) => {
    setActivityQuery((previous) => ({ ...previous, page: 1, pageSize }));
  };

  const clearFilters = () => {
    setSearchInput('');
    setActivityQuery((previous) => ({
      ...previous,
      page: 1,
      search: '',
      action: '',
      status: '',
    }));
  };

  const toggleSort = (nextSortBy: UserDetailActivitySortKey) => {
    const nextSortDir: UserDetailSortDirection =
      query.sortBy === nextSortBy ? (query.sortDir === 'asc' ? 'desc' : 'asc') : 'desc';

    setActivityQuery((previous) => ({
      ...previous,
      page: 1,
      sortBy: nextSortBy,
      sortDir: nextSortDir,
    }));
  };

  const activityRows = detail.recent_activity;
  const pagination = detail.recent_activity_pagination;
  const activityTotalItems = pagination.total;
  const activityTotalPages = Math.max(1, Math.ceil(activityTotalItems / pagination.page_size));
  const safeActivityPage = Math.min(pagination.page, activityTotalPages);

  const activityShowingFrom = activityTotalItems === 0 ? 0 : (safeActivityPage - 1) * pagination.page_size + 1;
  const activityShowingTo = Math.min(
    (safeActivityPage - 1) * pagination.page_size + activityRows.length,
    activityTotalItems
  );
  const hasActivityFilters = Boolean(searchInput.trim() || query.action || query.status);

  return (
    <SectionCard
      headerClassName="flex-wrap items-start gap-3"
      title={
        <div className="flex items-center gap-2">
          <FiActivity className="h-4 w-4 text-app-accent" />
          <span>Recent Activity</span>
        </div>
      }
      action={
        <div className="flex flex-wrap items-center justify-end gap-2">
          <label className="relative block w-[300px] max-w-full">
            <FiSearch className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-subtle" />
            <input
              type="text"
              value={searchInput}
              onChange={(event) => setSearchInput(event.target.value)}
              placeholder="Search action, detail, or entity..."
              className="h-[40px] w-full rounded-xl border-0 bg-surface-muted pl-9 pr-9 text-sm text-text-secondary outline-none transition focus:ring-2 focus:ring-option-selected-ring placeholder:text-subtle"
            />
            {searchInput ? (
              <button
                type="button"
                onClick={() => {
                  setSearchInput('');
                  setActivityQuery((previous) => ({ ...previous, page: 1, search: '' }));
                }}
                aria-label="Clear activity search"
                className="absolute right-2.5 top-1/2 -translate-y-1/2 text-subtle transition hover:text-text-secondary"
              >
                <FiX className="h-3.5 w-3.5" />
              </button>
            ) : null}
          </label>
          <div className="min-w-[170px]">
            <SelectDropdown
              value={query.action}
              onChange={(value) => setActionFilter(value as UserDetailActivityAction | '')}
              options={ACTIVITY_ACTION_OPTIONS}
              className="w-full [&>button]:h-[40px] [&>button]:py-0"
            />
          </div>
          <div className="min-w-[170px]">
            <SelectDropdown
              value={query.status}
              onChange={(value) => setStatusFilter(value as UserDetailActivityStatusFilter | '')}
              options={ACTIVITY_STATUS_OPTIONS}
              className="w-full [&>button]:h-[40px] [&>button]:py-0"
            />
          </div>
        </div>
      }
    >
      <div className="mb-3 flex items-center justify-between gap-2">
        <p className="text-xs text-muted">
          Showing {formatAnalyticsNumber(activityShowingFrom)}–{formatAnalyticsNumber(activityShowingTo)} of{' '}
          {formatAnalyticsNumber(activityTotalItems)} activity items
        </p>
        {hasActivityFilters ? (
          <button
            type="button"
            onClick={clearFilters}
            className="text-xs font-medium text-app-accent-text transition hover:underline"
          >
            Clear filters
          </button>
        ) : null}
      </div>

      <div className="overflow-x-auto rounded-2xl border border-border/70">
        <table className="min-w-full table-fixed border-collapse">
          <thead className="bg-surface-muted/75">
            <tr>
              <th className="w-[17%] px-4 py-3 text-left">
                <SortableHeader
                  label="Action"
                  sortKey="action"
                  activeSortKey={query.sortBy}
                  sortDir={query.sortDir}
                  onToggle={toggleSort}
                />
              </th>
              <th className="w-[33%] px-4 py-3 text-left text-[11px] font-semibold uppercase tracking-[0.12em] text-muted">
                Detail
              </th>
              <th className="w-[11%] px-4 py-3 text-left">
                <SortableHeader
                  label="Status"
                  sortKey="status"
                  activeSortKey={query.sortBy}
                  sortDir={query.sortDir}
                  onToggle={toggleSort}
                />
              </th>
              <th className="w-[10%] px-4 py-3 text-left">
                <SortableHeader
                  label="Duration"
                  sortKey="duration"
                  activeSortKey={query.sortBy}
                  sortDir={query.sortDir}
                  onToggle={toggleSort}
                />
              </th>
              <th className="w-[13%] px-4 py-3 text-left">
                <SortableHeader
                  label="Occurred"
                  sortKey="occurred"
                  activeSortKey={query.sortBy}
                  sortDir={query.sortDir}
                  onToggle={toggleSort}
                />
              </th>
              <th className="w-[16%] px-4 py-3 text-left">
                <SortableHeader
                  label="Entity"
                  sortKey="entity"
                  activeSortKey={query.sortBy}
                  sortDir={query.sortDir}
                  onToggle={toggleSort}
                />
              </th>
            </tr>
          </thead>
          <tbody>
            {activityRows.length ? (
              activityRows.map((entry) => (
                <tr key={entry.id} className="border-t border-border/70">
                  <td className="px-4 py-3">
                    <span className="rounded-full bg-app-accent-soft px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-app-accent-text">
                      {toTitleCase(entry.action)}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <p className="truncate text-xs text-text-secondary" title={entry.detail || ''}>
                      {entry.detail || '--'}
                    </p>
                  </td>
                  <td className="px-4 py-3">
                    {entry.status ? (
                      <span
                        className={`rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${getStatusBadgeClass(entry.status as UserDetailActivityStatus)}`}
                      >
                        {entry.status}
                      </span>
                    ) : (
                      <span className="text-xs text-subtle">--</span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-xs whitespace-nowrap text-subtle">
                    {entry.duration_ms === null ? '--' : formatDurationMs(entry.duration_ms)}
                  </td>
                  <td className="px-4 py-3 text-xs whitespace-nowrap text-subtle">
                    {formatRelativeActivityTime(entry.occurred_at)}
                  </td>
                  <td className="px-4 py-3 text-xs text-subtle">
                    <p className="truncate" title={entry.entity_id || ''}>
                      {entry.entity_id || '--'}
                    </p>
                  </td>
                </tr>
              ))
            ) : (
              <tr>
                <td colSpan={6} className="px-4 py-8 text-center text-sm text-muted">
                  No activity found for this filter set.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {activityTotalItems ? (
        <AnalyticsTablePaginationFooter
          page={safeActivityPage}
          totalPages={activityTotalPages}
          pageSize={query.pageSize}
          pageSizeOptions={DETAIL_PAGE_SIZE_OPTIONS}
          onPageChange={setPage}
          onPageSizeChange={setPageSize}
          className="mt-3"
          keyPrefix="activity-pagination"
        />
      ) : null}
    </SectionCard>
  );
};
