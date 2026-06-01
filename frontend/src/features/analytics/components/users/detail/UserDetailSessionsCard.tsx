import React, { useEffect, useState } from 'react';
import { FiFolder, FiSearch, FiX } from 'react-icons/fi';
import { SelectDropdown } from '@/components/common';
import { AnalyticsTablePaginationFooter } from '@/features/analytics/components/AnalyticsTablePaginationFooter';
import { SectionCard } from '@/features/analytics/components/SectionCard';
import { SortableHeader } from '@/features/analytics/components/SortableHeader';
import { useUserDetailPageContext } from './UserDetailPageContext';
import type {
  UserDetailSessionSource,
  UserDetailSessionStatus,
  UserDetailSessionsSortKey,
  UserDetailSortDirection,
} from '@/features/analytics/types';
import { formatRelativeActivityTime } from '@/features/analytics/utils/activityFeed.helpers';
import { formatDistrictLabel } from '@/features/analytics/utils/districtLabels';
import { formatAnalyticsNumber } from '@/features/analytics/utils/dashboard.mappers';
import {
  DETAIL_PAGE_SIZE_OPTIONS,
  getSessionStatusBadgeClass,
  SESSION_SOURCE_OPTIONS,
  SESSION_STATUS_OPTIONS,
  toTitleCase,
} from '@/features/analytics/utils/userDetail.helpers';

export const UserDetailSessionsCard: React.FC = () => {
  const { detail, sessionsQuery: query, setSessionsQuery } = useUserDetailPageContext();
  const [searchInput, setSearchInput] = useState(query.search);

  useEffect(() => {
    setSearchInput(query.search);
  }, [query.search]);

  useEffect(() => {
    const timeout = window.setTimeout(() => {
      const trimmed = searchInput.trim();
      if (trimmed !== query.search) {
        setSessionsQuery((previous) => ({ ...previous, page: 1, search: trimmed }));
      }
    }, 300);
    return () => window.clearTimeout(timeout);
  }, [searchInput, query.search, setSessionsQuery]);

  const setSourceFilter = (source: UserDetailSessionSource | '') => {
    setSessionsQuery((previous) => ({ ...previous, page: 1, source }));
  };

  const setStatusFilter = (status: UserDetailSessionStatus | '') => {
    setSessionsQuery((previous) => ({ ...previous, page: 1, status }));
  };

  const setPage = (page: number) => {
    setSessionsQuery((previous) => ({ ...previous, page }));
  };

  const setPageSize = (pageSize: number) => {
    setSessionsQuery((previous) => ({ ...previous, page: 1, pageSize }));
  };

  const clearFilters = () => {
    setSearchInput('');
    setSessionsQuery((previous) => ({
      ...previous,
      page: 1,
      search: '',
      source: '',
      status: '',
    }));
  };

  const toggleSort = (nextSortBy: UserDetailSessionsSortKey) => {
    const nextSortDir: UserDetailSortDirection =
      query.sortBy === nextSortBy ? (query.sortDir === 'asc' ? 'desc' : 'asc') : 'desc';

    setSessionsQuery((previous) => ({
      ...previous,
      page: 1,
      sortBy: nextSortBy,
      sortDir: nextSortDir,
    }));
  };

  const sessions = detail.recent_sessions;
  const pagination = detail.recent_sessions_pagination;
  const sessionTotalItems = pagination.total;
  const sessionTotalPages = Math.max(1, Math.ceil(sessionTotalItems / pagination.page_size));
  const safeSessionPage = Math.min(pagination.page, sessionTotalPages);

  const sessionShowingFrom = sessionTotalItems === 0 ? 0 : (safeSessionPage - 1) * pagination.page_size + 1;
  const sessionShowingTo = Math.min(
    (safeSessionPage - 1) * pagination.page_size + sessions.length,
    sessionTotalItems
  );

  const hasFilters = Boolean(searchInput.trim() || query.source || query.status);

  return (
    <SectionCard
      className="mb-6"
      headerClassName="flex-wrap items-start gap-3"
      title={
        <div className="flex items-center gap-2">
          <FiFolder className="h-4 w-4 text-app-accent" />
          <span>Recent Sessions</span>
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
              placeholder="Search case #, debtor, district, or session..."
              className="h-[40px] w-full rounded-xl border-0 bg-surface-muted pl-9 pr-9 text-sm text-text-secondary outline-none transition focus:ring-2 focus:ring-option-selected-ring placeholder:text-subtle"
            />
            {searchInput ? (
              <button
                type="button"
                onClick={() => {
                  setSearchInput('');
                  setSessionsQuery((previous) => ({ ...previous, page: 1, search: '' }));
                }}
                aria-label="Clear session search"
                className="absolute right-2.5 top-1/2 -translate-y-1/2 text-subtle transition hover:text-text-secondary"
              >
                <FiX className="h-3.5 w-3.5" />
              </button>
            ) : null}
          </label>
          <div className="min-w-[170px]">
            <SelectDropdown
              value={query.source}
              onChange={(value) => setSourceFilter(value as UserDetailSessionSource | '')}
              options={SESSION_SOURCE_OPTIONS}
              className="w-full [&>button]:h-[40px] [&>button]:py-0"
            />
          </div>
          <div className="min-w-[180px]">
            <SelectDropdown
              value={query.status}
              onChange={(value) => setStatusFilter(value as UserDetailSessionStatus | '')}
              options={SESSION_STATUS_OPTIONS}
              className="w-full [&>button]:h-[40px] [&>button]:py-0"
            />
          </div>
        </div>
      }
    >
      <div className="mb-3 flex items-center justify-between gap-2">
        <p className="text-xs text-muted">
          Showing {formatAnalyticsNumber(sessionShowingFrom)}–{formatAnalyticsNumber(sessionShowingTo)} of{' '}
          {formatAnalyticsNumber(sessionTotalItems)} sessions
        </p>
        {hasFilters ? (
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
              <th className="w-[20%] px-4 py-3 text-left">
                <SortableHeader
                  label="Case"
                  sortKey="case"
                  activeSortKey={query.sortBy}
                  sortDir={query.sortDir}
                  onToggle={toggleSort}
                />
              </th>
              <th className="w-[11%] px-4 py-3 text-left">
                <SortableHeader
                  label="District"
                  sortKey="district"
                  activeSortKey={query.sortBy}
                  sortDir={query.sortDir}
                  onToggle={toggleSort}
                />
              </th>
              <th className="w-[12%] px-4 py-3 text-left">
                <SortableHeader
                  label="Source"
                  sortKey="source"
                  activeSortKey={query.sortBy}
                  sortDir={query.sortDir}
                  onToggle={toggleSort}
                />
              </th>
              <th className="w-[14%] px-4 py-3 text-left">
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
                  label="Motions"
                  sortKey="motions"
                  activeSortKey={query.sortBy}
                  sortDir={query.sortDir}
                  onToggle={toggleSort}
                />
              </th>
              <th className="w-[20%] px-4 py-3 text-left">
                <SortableHeader
                  label="Last Activity"
                  sortKey="last_activity"
                  activeSortKey={query.sortBy}
                  sortDir={query.sortDir}
                  onToggle={toggleSort}
                />
              </th>
              <th className="w-[13%] px-4 py-3 text-left text-[11px] font-semibold uppercase tracking-[0.12em] text-muted">
                Session ID
              </th>
            </tr>
          </thead>
          <tbody>
            {sessions.length ? (
              sessions.map((session) => (
                <tr key={session.session_id} className="border-t border-border/70">
                  <td className="px-4 py-3">
                    <p className="truncate text-sm font-semibold text-text">{session.case_number || '--'}</p>
                    <p className="truncate text-xs text-muted">{session.debtor_name || '--'}</p>
                  </td>
                  <td className="px-4 py-3 text-xs text-muted">{formatDistrictLabel(session.district)}</td>
                  <td className="px-4 py-3 text-xs text-muted">{toTitleCase(session.source || 'manual')}</td>
                  <td className="px-4 py-3">
                    {session.petition_status ? (
                      <span
                        className={`rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${getSessionStatusBadgeClass(session.petition_status)}`}
                      >
                        {toTitleCase(session.petition_status)}
                      </span>
                    ) : (
                      <span className="text-xs text-subtle">--</span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-sm font-semibold text-text">
                    {formatAnalyticsNumber(session.motions_count)}
                  </td>
                  <td className="px-4 py-3 text-xs text-muted">
                    {session.last_activity_at ? formatRelativeActivityTime(session.last_activity_at) : '--'}
                  </td>
                  <td className="px-4 py-3 text-xs text-subtle">{session.session_id}</td>
                </tr>
              ))
            ) : (
              <tr>
                <td colSpan={7} className="px-4 py-8 text-center text-sm text-muted">
                  No sessions found for this filter set.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {sessionTotalItems ? (
        <AnalyticsTablePaginationFooter
          page={safeSessionPage}
          totalPages={sessionTotalPages}
          pageSize={query.pageSize}
          pageSizeOptions={DETAIL_PAGE_SIZE_OPTIONS}
          onPageChange={setPage}
          onPageSizeChange={setPageSize}
          className="mt-3"
          keyPrefix="sessions-pagination"
        />
      ) : null}
    </SectionCard>
  );
};
