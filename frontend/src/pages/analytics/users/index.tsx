import React, { useEffect, useMemo, useState } from 'react';
import type { MouseEvent } from 'react';
import { FiDownload, FiSearch, FiTrendingUp, FiUsers, FiX } from 'react-icons/fi';
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { useNavigate } from 'react-router-dom';
import { AnalyticsBodySkeleton } from '@/features/analytics/components/AnalyticsSkeleton';
import { AnalyticsTablePaginationFooter } from '@/features/analytics/components/AnalyticsTablePaginationFooter';
import { KpiSurface } from '@/features/analytics/components/KpiSurface';
import { SectionCard } from '@/features/analytics/components/SectionCard';
import { SortableHeader } from '@/features/analytics/components/SortableHeader';
import {
  chartLineCursorStyle,
  chartTooltipWrapperStyle,
} from '@/features/analytics/components/chartStyles';
import { AnalyticsChartTooltip } from '@/features/analytics/components/chartShared';
import { AnalyticsLayout } from '@/features/analytics/components/shared';
import { useAnalyticsQueryFilters } from '@/features/analytics/hooks/useAnalyticsQueryFilters';
import { useDashboardAnalyticsUsers } from '@/features/analytics/hooks/useDashboardAnalyticsUsers';
import { useDashboardUsersDaily } from '@/features/analytics/hooks/useDashboardUsersDaily';
import { useUsersExportActions } from '@/features/analytics/hooks/useUsersExportActions';
import { useAnalyticsFiltersStore } from '@/features/analytics/stores/useAnalyticsFiltersStore';
import type {
  DashboardUsersAnalyticsQuery,
  DashboardUsersAnalyticsUser,
  SortDirection,
  UsersSummaryMetrics,
  UsersTableSortKey,
  UsersTrendPoint,
} from '@/features/analytics/types';
import { formatAnalyticsNumber } from '@/features/analytics/utils/dashboard.mappers';
import {
  CHART_COLORS,
  PAGE_SIZE_OPTIONS,
  formatChartDay,
  formatDate,
  formatDuration,
  formatRelativeDate,
  getDisplayName,
  getInitials,
  resolveServerSortBy,
} from '@/features/analytics/utils/usersList.helpers';
import { useToastStore } from '@/stores/useToastStore';

export const AnalyticsUsersPage: React.FC = () => {
  const navigate = useNavigate();
  const { rangePreset } = useAnalyticsFiltersStore();
  const analyticsFilters = useAnalyticsQueryFilters();
  const addToast = useToastStore((state) => state.addToast);
  const [searchInput, setSearchInput] = useState('');
  const [searchQuery, setSearchQuery] = useState('');
  const [sortKey, setSortKey] = useState<UsersTableSortKey>('last_active');
  const [sortDir, setSortDir] = useState<SortDirection>('desc');
  const [pageSize, setPageSize] = useState<number>(10);
  const [page, setPage] = useState<number>(1);

  const trimmedSearchInput = useMemo(() => searchInput.trim(), [searchInput]);

  useEffect(() => {
    const timeout = window.setTimeout(() => {
      setSearchQuery((currentValue) =>
        currentValue === trimmedSearchInput ? currentValue : trimmedSearchInput
      );
    }, 350);

    return () => window.clearTimeout(timeout);
  }, [trimmedSearchInput]);

  useEffect(() => {
    setPage(1);
  }, [rangePreset, searchQuery, sortKey, sortDir, pageSize]);

  const serverSortBy = resolveServerSortBy(sortKey);

  const usersQuery = useMemo<DashboardUsersAnalyticsQuery>(
    () => ({
      page,
      page_size: pageSize,
      sort_by: serverSortBy,
      sort_dir: sortDir,
      ...(searchQuery ? { search: searchQuery } : {}),
    }),
    [page, pageSize, searchQuery, serverSortBy, sortDir]
  );

  const { data, isLoading, isFetching, error } = useDashboardAnalyticsUsers(usersQuery);
  const {
    data: usersDailyData,
    isLoading: isUsersDailyLoading,
    isFetching: isUsersDailyFetching,
    error: usersDailyError,
  } = useDashboardUsersDaily();

  const totalItems = data?.pagination.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(totalItems / pageSize));

  useEffect(() => {
    if (page > totalPages) {
      setPage(totalPages);
    }
  }, [page, totalPages]);

  const summary: UsersSummaryMetrics = {
    totalUsers: data?.kpis.total_users ?? 0,
    newInRange: data?.kpis.new_in_range ?? 0,
    activeInRange: data?.kpis.active_in_range ?? 0,
    avgMotionsPerUser: data?.kpis.avg_motions_per_user ?? 0,
  };

  const chartData: UsersTrendPoint[] = useMemo(() => {
    return (usersDailyData?.data ?? []).map((point) => ({
      day: formatChartDay(point.date),
      motions: point.motions_drafted,
      activeUsers: point.active_users,
      newUsers: point.new_users,
    }));
  }, [usersDailyData?.data]);

  const showingFrom = totalItems === 0 ? 0 : (page - 1) * pageSize + 1;
  const showingTo = Math.min(page * pageSize, totalItems);
  const hasUsersData = Boolean(data);
  const showUsersTableSkeleton = isLoading || isFetching;
  const hasActiveFilters = Boolean(searchInput.trim());
  const rows = data?.users ?? [];

  const { exportingUserId, handleExportSingleUserXlsx, handleExportUsersXlsx, isExporting } =
    useUsersExportActions({
      addToast,
      analyticsFilters,
      searchQuery,
      sortBy: serverSortBy,
      sortDir,
    });

  const handleHeaderSortToggle = (nextSortKey: UsersTableSortKey) => {
    setSortDir((current) => {
      if (sortKey === nextSortKey) {
        return current === 'asc' ? 'desc' : 'asc';
      }

      return 'desc';
    });
    setSortKey(nextSortKey);
  };

  const handleClearFilters = () => {
    setSearchInput('');
    setSearchQuery('');
    setPage(1);
  };

  const handleOpenUserDetail = (
    user: DashboardUsersAnalyticsUser,
    event: MouseEvent<HTMLButtonElement>
  ) => {
    event.stopPropagation();
    navigate(`/analytics/users/${encodeURIComponent(user.user_id)}`);
  };

  const handleRowActivate = (user: DashboardUsersAnalyticsUser) => {
    navigate(`/analytics/users/${encodeURIComponent(user.user_id)}`);
  };

  return (
    <AnalyticsLayout title="User Analytics">
      <section className="mb-8 grid gap-8 xl:grid-cols-[minmax(0,1fr)_minmax(0,2fr)]">
        <div className="grid gap-4 sm:grid-cols-2">
          <KpiSurface
            label="Total Users"
            value={formatAnalyticsNumber(summary.totalUsers)}
            iconKey="totalUsers"
            loading={isLoading && !hasUsersData}
          />
          <KpiSurface
            label="New In Range"
            value={formatAnalyticsNumber(summary.newInRange)}
            iconKey="newUsers"
            valueClass="text-app-accent-text"
            loading={isLoading && !hasUsersData}
          />
          <KpiSurface
            label="Active In Range"
            value={formatAnalyticsNumber(summary.activeInRange)}
            iconKey="activeCases"
            valueClass="text-app-success-text"
            loading={isLoading && !hasUsersData}
          />
          <KpiSurface
            label="Avg Motions / User"
            value={formatAnalyticsNumber(summary.avgMotionsPerUser, {
              maximumFractionDigits: 1,
            })}
            iconKey="motionsDrafted"
            valueClass="text-app-warning-text"
            loading={isLoading && !hasUsersData}
          />
        </div>

        <SectionCard
          title={
            <div className="flex items-center gap-2">
              <FiTrendingUp className="h-4 w-4 text-app-accent" />
              <span>Daily Activity Trend</span>
            </div>
          }
          action={
            <div className="flex items-center gap-4 text-[11px] text-muted">
              <span className="inline-flex items-center gap-1.5">
                <span
                  className="h-2.5 w-2.5 rounded-full"
                  style={{ backgroundColor: CHART_COLORS.motions }}
                />
                Motions drafted
              </span>
              <span className="inline-flex items-center gap-1.5">
                <span
                  className="h-2.5 w-2.5 rounded-full"
                  style={{ backgroundColor: CHART_COLORS.activeUsers }}
                />
                Active users
              </span>
              <span className="inline-flex items-center gap-1.5">
                <span
                  className="h-2.5 w-2.5 rounded-full"
                  style={{ backgroundColor: CHART_COLORS.newUsers }}
                />
                New users
              </span>
            </div>
          }
        >
          {usersDailyError ? (
            <div className="rounded-2xl border border-app-danger-text/30 bg-app-danger-soft px-4 py-3 text-sm text-app-danger-text">
              Failed to load users trend: {usersDailyError.message}
            </div>
          ) : isUsersDailyLoading || isUsersDailyFetching ? (
            <AnalyticsBodySkeleton className="h-56" />
          ) : chartData.length === 0 ? (
            <div className="flex h-56 items-center justify-center rounded-2xl border border-border/70 bg-surface-muted/60">
              <p className="text-sm text-muted">No users trend data for this date range.</p>
            </div>
          ) : (
            <div className="h-56">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={chartData} margin={{ top: 8, right: 8, left: -20, bottom: 0 }}>
                  <CartesianGrid stroke="var(--app-chart-grid)" vertical={false} />
                  <XAxis
                    dataKey="day"
                    axisLine={false}
                    tickLine={false}
                    tick={{ fill: 'var(--app-chart-axis)', fontSize: 11 }}
                  />
                  <YAxis
                    axisLine={false}
                    tickLine={false}
                    tick={{ fill: 'var(--app-chart-axis)', fontSize: 11 }}
                  />
                  <Tooltip
                    content={<AnalyticsChartTooltip />}
                    wrapperStyle={chartTooltipWrapperStyle}
                    cursor={chartLineCursorStyle}
                  />
                  <Line
                    type="monotone"
                    dataKey="motions"
                    name="Motions drafted"
                    stroke={CHART_COLORS.motions}
                    strokeWidth={2.5}
                    dot={false}
                    activeDot={{
                      r: 5,
                      stroke: 'var(--app-bg-surface)',
                      strokeWidth: 2,
                      fill: CHART_COLORS.motions,
                    }}
                  />
                  <Line
                    type="monotone"
                    dataKey="activeUsers"
                    name="Active users"
                    stroke={CHART_COLORS.activeUsers}
                    strokeWidth={2.5}
                    dot={false}
                    activeDot={{
                      r: 5,
                      stroke: 'var(--app-bg-surface)',
                      strokeWidth: 2,
                      fill: CHART_COLORS.activeUsers,
                    }}
                  />
                  <Line
                    type="monotone"
                    dataKey="newUsers"
                    name="New users"
                    stroke={CHART_COLORS.newUsers}
                    strokeWidth={2.25}
                    dot={false}
                    activeDot={{
                      r: 5,
                      stroke: 'var(--app-bg-surface)',
                      strokeWidth: 2,
                      fill: CHART_COLORS.newUsers,
                    }}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}
        </SectionCard>
      </section>

      <SectionCard
        className="mb-8"
        title={
          <div className="flex items-center gap-2">
            <FiUsers className="h-4 w-4 text-app-accent" />
            <span>Users</span>
          </div>
        }
        action={
          <div className="flex flex-wrap items-center gap-2">
            <label className="relative block min-w-[320px]">
              <FiSearch className="pointer-events-none absolute left-4 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-subtle" />
              <input
                type="text"
                value={searchInput}
                onChange={(event) => setSearchInput(event.target.value)}
                placeholder="Search name or email..."
                className="h-[40px] w-full rounded-xl border-0 bg-surface-muted pl-10 pr-11 text-sm text-text-secondary outline-none transition focus:ring-2 focus:ring-option-selected-ring placeholder:text-subtle"
              />
              {searchInput.length ? (
                <button
                  type="button"
                  onClick={handleClearFilters}
                  aria-label="Clear search"
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-subtle transition hover:text-text-secondary"
                >
                  <FiX className="h-3.5 w-3.5" />
                </button>
              ) : null}
            </label>
            <button
              type="button"
              onClick={() => void handleExportUsersXlsx()}
              disabled={isExporting || Boolean(exportingUserId)}
              className="inline-flex h-[40px] items-center gap-2 rounded-xl border border-border bg-surface-muted px-3.5 py-0 text-sm font-medium text-text-secondary transition hover:bg-surface disabled:cursor-not-allowed disabled:opacity-60"
            >
              <FiDownload className="h-4 w-4" />
              {isExporting ? 'Exporting…' : 'Export View XLSX'}
            </button>
          </div>
        }
      >
        {error ? (
          <div className="rounded-2xl border border-app-danger-text/30 bg-app-danger-soft px-4 py-3 text-sm text-app-danger-text">
            Failed to load user analytics: {error.message}
          </div>
        ) : (
          <>
            <div className="mb-3 flex items-center justify-between gap-2">
              {showUsersTableSkeleton ? (
                <AnalyticsBodySkeleton className="h-4 max-w-44" />
              ) : (
                <p className="text-xs text-muted">
                  Showing {showingFrom}–{showingTo} of {formatAnalyticsNumber(totalItems)} users
                </p>
              )}
              {hasActiveFilters ? (
                <button
                  type="button"
                  onClick={handleClearFilters}
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
                    <th className="w-[28%] px-4 py-3 text-left whitespace-nowrap">
                      <span className="inline-flex items-center whitespace-nowrap text-[11px] font-semibold uppercase tracking-[0.12em] text-muted">
                        User
                      </span>
                    </th>
                    <th className="w-[11%] px-4 py-3 text-left whitespace-nowrap">
                      <SortableHeader
                        label="Joined"
                        sortKey="joined"
                        activeSortKey={sortKey}
                        sortDir={sortDir}
                        onToggle={handleHeaderSortToggle}
                      />
                    </th>
                    <th className="w-[14%] px-4 py-3 text-left whitespace-nowrap">
                      <SortableHeader
                        label="Last Active"
                        sortKey="last_active"
                        activeSortKey={sortKey}
                        sortDir={sortDir}
                        onToggle={handleHeaderSortToggle}
                      />
                    </th>
                    <th className="w-[8%] px-4 py-3 text-left whitespace-nowrap">
                      <SortableHeader
                        label="Cases"
                        sortKey="cases"
                        activeSortKey={sortKey}
                        sortDir={sortDir}
                        onToggle={handleHeaderSortToggle}
                      />
                    </th>
                    <th className="w-[8%] px-4 py-3 text-left whitespace-nowrap">
                      <SortableHeader
                        label="Motions"
                        sortKey="motions"
                        activeSortKey={sortKey}
                        sortDir={sortDir}
                        onToggle={handleHeaderSortToggle}
                      />
                    </th>
                    <th className="w-[10%] px-4 py-3 text-left whitespace-nowrap">
                      <span className="inline-flex items-center whitespace-nowrap text-[11px] font-semibold uppercase tracking-[0.12em] text-muted">
                        Avg Draft
                      </span>
                    </th>
                    <th className="w-[18%] px-4 py-3 text-left whitespace-nowrap">
                      <span className="inline-flex items-center whitespace-nowrap text-[11px] font-semibold uppercase tracking-[0.12em] text-muted">
                        Top Types
                      </span>
                    </th>
                    <th className="w-[12%] px-4 py-3 text-left whitespace-nowrap">
                      <span className="inline-flex items-center whitespace-nowrap text-[11px] font-semibold uppercase tracking-[0.12em] text-muted">
                        Actions
                      </span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {showUsersTableSkeleton ? (
                    Array.from({ length: 3 }).map((_, index) => (
                      <tr key={`users-skeleton-${index}`} className="border-t border-border/70">
                        <td className="px-4 py-3">
                          <AnalyticsBodySkeleton className="h-5 w-full" />
                        </td>
                        <td className="px-4 py-3">
                          <AnalyticsBodySkeleton className="h-5 w-20" />
                        </td>
                        <td className="px-4 py-3">
                          <AnalyticsBodySkeleton className="h-5 w-20" />
                        </td>
                        <td className="px-4 py-3">
                          <AnalyticsBodySkeleton className="h-5 w-10" />
                        </td>
                        <td className="px-4 py-3">
                          <AnalyticsBodySkeleton className="h-5 w-10" />
                        </td>
                        <td className="px-4 py-3">
                          <AnalyticsBodySkeleton className="h-5 w-14" />
                        </td>
                        <td className="px-4 py-3">
                          <AnalyticsBodySkeleton className="h-5 w-full" />
                        </td>
                        <td className="px-4 py-3">
                          <AnalyticsBodySkeleton className="h-5 w-20" />
                        </td>
                      </tr>
                    ))
                  ) : rows.length ? (
                    rows.map((user) => {
                      return (
                        <tr
                          key={user.user_id}
                          onClick={() => handleRowActivate(user)}
                          onKeyDown={(event) => {
                            if (event.key === 'Enter' || event.key === ' ') {
                              event.preventDefault();
                              handleRowActivate(user);
                            }
                          }}
                          role="button"
                          tabIndex={0}
                          aria-label={`Open user details for ${getDisplayName(user)}`}
                          className="cursor-pointer border-t border-border/70 transition-colors hover:bg-activity-row-hover"
                        >
                          <td className="px-4 py-3">
                            <div className="flex items-center gap-2.5">
                              <div className="flex h-8 w-8 items-center justify-center rounded-full bg-app-accent-soft text-[11px] font-semibold text-app-accent-text">
                                {getInitials(user)}
                              </div>
                              <div className="min-w-0">
                                <p className="truncate text-sm font-semibold text-text">
                                  {getDisplayName(user)}
                                </p>
                                <p className="truncate text-xs text-muted">{user.email}</p>
                              </div>
                            </div>
                          </td>
                          <td className="px-4 py-3 text-xs text-muted">
                            {formatDate(user.created_at)}
                          </td>
                          <td className="px-4 py-3 text-xs text-muted">
                            {formatRelativeDate(user.last_active_at)}
                          </td>
                          <td className="px-4 py-3 text-sm font-semibold text-text">
                            {formatAnalyticsNumber(user.cases_count)}
                          </td>
                          <td className="px-4 py-3 text-sm font-semibold text-text">
                            {formatAnalyticsNumber(user.motions_drafted)}
                          </td>
                          <td className="px-4 py-3 text-xs text-muted">
                            {formatDuration(user.avg_draft_time_seconds)}
                          </td>
                          <td className="px-4 py-3">
                            <div className="flex flex-wrap gap-1">
                              {user.top_motion_types.length ? (
                                user.top_motion_types.slice(0, 3).map((motionType) => (
                                  <span
                                    key={`${user.user_id}-${motionType}`}
                                    className="rounded-full border border-border bg-surface-muted/80 px-2 py-0.5 text-[10px] text-muted"
                                  >
                                    {motionType}
                                  </span>
                                ))
                              ) : (
                                <span className="text-[11px] text-subtle">
                                  No completed motions yet
                                </span>
                              )}
                            </div>
                          </td>
                          <td className="px-4 py-3">
                            <div className="flex items-center gap-1.5">
                              <button
                                type="button"
                                onClick={(event) => handleOpenUserDetail(user, event)}
                                className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-surface px-2.5 py-1.5 text-[11px] font-medium text-text-secondary transition hover:bg-surface-muted"
                                aria-label={`Open details for ${getDisplayName(user)}`}
                              >
                                Details
                              </button>
                              <button
                                type="button"
                                onClick={(event) => void handleExportSingleUserXlsx(user, event)}
                                disabled={isExporting || Boolean(exportingUserId)}
                                className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-surface px-2.5 py-1.5 text-[11px] font-medium text-text-secondary transition hover:bg-surface-muted disabled:cursor-not-allowed disabled:opacity-60"
                                aria-label={`Export XLSX for ${getDisplayName(user)}`}
                              >
                                <FiDownload className="h-3.5 w-3.5" />
                                {exportingUserId === user.user_id ? 'Exporting…' : 'Export'}
                              </button>
                            </div>
                          </td>
                        </tr>
                      );
                    })
                  ) : (
                    <tr>
                      <td colSpan={8} className="px-4 py-8 text-center text-sm text-muted">
                        No users found for this filter set.
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
              pageSizeOptions={PAGE_SIZE_OPTIONS}
              onPageChange={setPage}
              onPageSizeChange={setPageSize}
              className="mt-4"
              keyPrefix="users-pagination"
            />
          </>
        )}
      </SectionCard>
    </AnalyticsLayout>
  );
};
