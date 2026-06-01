import React, { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { FiChevronDown, FiChevronUp, FiFileText, FiSearch, FiX } from 'react-icons/fi';
import { SelectDropdown } from '@/components/common';
import { AnalyticsBodySkeleton } from '@/features/analytics/components/AnalyticsSkeleton';
import { AnalyticsTablePaginationFooter } from '@/features/analytics/components/AnalyticsTablePaginationFooter';
import { KpiSurface } from '@/features/analytics/components/KpiSurface';
import { SectionCard } from '@/features/analytics/components/SectionCard';
import { SortableHeader } from '@/features/analytics/components/SortableHeader';
import { useDashboardAnalyticsMotions } from '@/features/analytics/hooks/useDashboardAnalyticsMotions';
import { useAnalyticsFiltersStore } from '@/features/analytics/stores/useAnalyticsFiltersStore';
import { AnalyticsLayout } from '@/features/analytics/components/shared';
import type {
  DashboardCaseSource,
  DashboardMotionAnalyticsItem,
  DashboardMotionCategory,
  DashboardMotionCosType,
  DashboardMotionStatus,
} from '@/features/analytics/types/dashboard.types';
import {
  DISTRICT_FILTER_KEYS,
  formatDistrictLabel,
  getDistrictCode,
  getDistrictName,
} from '@/features/analytics/utils/districtLabels';
import { formatAnalyticsNumber } from '@/features/analytics/utils/dashboard.mappers';
import {
  MOTIONS_CATEGORY_OPTIONS,
  MOTIONS_COS_TYPE_OPTIONS,
  MOTIONS_PAGE_SIZE_OPTIONS,
  MOTIONS_SOURCE_OPTIONS,
  MOTIONS_STATUS_OPTIONS,
  type MotionsTableSortKey,
  formatMotionCosType,
  formatMotionDateTime,
  formatMotionProcessing,
  formatMotionsLabel,
  getMotionCategoryBadgeClass,
  getMotionCosBadgeClass,
  getMotionStatusBadgeClass,
  resolveMotionsServerSortBy,
} from '@/features/analytics/utils/motionsList.helpers';

type SortDirection = 'asc' | 'desc';

const DISTRICT_FALLBACK_OPTIONS = [
  { label: 'All districts', value: '' },
  ...DISTRICT_FILTER_KEYS.map((district) => ({
    label: formatDistrictLabel(district),
    value: district,
  })),
];

export const AnalyticsMotionsPage: React.FC = () => {
  const navigate = useNavigate();
  const { rangePreset } = useAnalyticsFiltersStore();
  const [searchInput, setSearchInput] = useState('');
  const [searchQuery, setSearchQuery] = useState('');
  const [motionTypeFilter, setMotionTypeFilter] = useState('');
  const [categoryFilter, setCategoryFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [districtFilter, setDistrictFilter] = useState('');
  const [sourceFilter, setSourceFilter] = useState('');
  const [cosTypeFilter, setCosTypeFilter] = useState('');
  const [showAdvancedFilters, setShowAdvancedFilters] = useState(false);
  const [pageSize, setPageSize] = useState<number>(10);
  const [page, setPage] = useState<number>(1);
  const [sortKey, setSortKey] = useState<MotionsTableSortKey>('created_at');
  const [sortDir, setSortDir] = useState<SortDirection>('desc');

  const trimmedSearchInput = useMemo(() => searchInput.trim(), [searchInput]);
  const hasActiveFilters = Boolean(
    searchInput.trim() ||
      motionTypeFilter ||
      categoryFilter ||
      statusFilter ||
      districtFilter ||
      sourceFilter ||
      cosTypeFilter
  );
  const advancedFilterCount =
    Number(Boolean(cosTypeFilter)) +
    Number(Boolean(districtFilter)) +
    Number(Boolean(sourceFilter));

  useEffect(() => {
    const timeout = window.setTimeout(() => {
      setSearchQuery((current) => (current === trimmedSearchInput ? current : trimmedSearchInput));
    }, 350);

    return () => window.clearTimeout(timeout);
  }, [trimmedSearchInput]);

  useEffect(() => {
    setPage(1);
  }, [
    rangePreset,
    searchQuery,
    motionTypeFilter,
    categoryFilter,
    statusFilter,
    districtFilter,
    sourceFilter,
    cosTypeFilter,
    pageSize,
    sortKey,
    sortDir,
  ]);

  const serverSortBy = resolveMotionsServerSortBy(sortKey);

  const listQuery = useMemo(
    () => ({
      page,
      page_size: pageSize,
      sort_by: serverSortBy,
      sort_dir: sortDir,
      ...(searchQuery ? { search: searchQuery } : {}),
      ...(motionTypeFilter ? { motion_type: motionTypeFilter } : {}),
      ...(categoryFilter ? { category: categoryFilter as DashboardMotionCategory } : {}),
      ...(statusFilter ? { status: statusFilter as DashboardMotionStatus } : {}),
      ...(districtFilter ? { district: districtFilter } : {}),
      ...(sourceFilter ? { source: sourceFilter as DashboardCaseSource } : {}),
      ...(cosTypeFilter ? { cos_type: cosTypeFilter as DashboardMotionCosType } : {}),
    }),
    [
      motionTypeFilter,
      categoryFilter,
      cosTypeFilter,
      districtFilter,
      page,
      pageSize,
      searchQuery,
      serverSortBy,
      sortDir,
      sourceFilter,
      statusFilter,
    ]
  );

  const { data, isLoading, isFetching, error } = useDashboardAnalyticsMotions(listQuery);
  const totalItems = data?.pagination.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(totalItems / pageSize));

  useEffect(() => {
    if (page > totalPages) {
      setPage(totalPages);
    }
  }, [page, totalPages]);

  const summary = {
    total: data?.kpis.total ?? 0,
    completed: data?.kpis.by_status.completed ?? 0,
    successRate: data?.kpis.success_rate_pct ?? 0,
    avgProcessingSeconds: data?.kpis.avg_processing_seconds ?? null,
  };

  const districtOptions = useMemo(() => {
    const byDistrict = data?.kpis.by_district;
    if (!byDistrict) {
      return DISTRICT_FALLBACK_OPTIONS;
    }

    const knownDistricts: Array<{ key: string; total: number }> = [
      { key: 'flnb', total: byDistrict.flnb.total_attempted },
      { key: 'flmb', total: byDistrict.flmb.total_attempted },
      { key: 'flsb', total: byDistrict.flsb.total_attempted },
      { key: 'pawb', total: byDistrict.pawb.total_attempted },
      { key: 'other', total: byDistrict.other.total_attempted },
    ];

    const populated = knownDistricts.filter((item) => item.total > 0).map((item) => item.key);
    const keys = populated.length ? populated : knownDistricts.map((item) => item.key);

    return [
      { label: 'All districts', value: '' },
      ...keys.map((district) => ({
        label: formatDistrictLabel(district),
        value: district,
      })),
    ];
  }, [data?.kpis.by_district]);

  const motionTypeOptions = useMemo(() => {
    const ranking = data?.kpis.motion_type_ranking ?? [];
    const byValue = new Map<string, string>();

    ranking.forEach((item) => {
      if (!byValue.has(item.motion_type)) {
        byValue.set(item.motion_type, item.display_name || formatMotionsLabel(item.motion_type));
      }
    });

    return [
      { label: 'All motion types', value: '' },
      ...Array.from(byValue.entries())
        .sort((left, right) => left[1].localeCompare(right[1]))
        .map(([value, label]) => ({ label, value })),
    ];
  }, [data?.kpis.motion_type_ranking]);

  const rows = data?.motions ?? [];

  const showingFrom = totalItems === 0 ? 0 : (page - 1) * pageSize + 1;
  const showingTo = Math.min(page * pageSize, totalItems);
  const showMotionsTableSkeleton = isLoading || isFetching;

  const handleHeaderSortToggle = (nextSortKey: MotionsTableSortKey) => {
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
    setMotionTypeFilter('');
    setCategoryFilter('');
    setStatusFilter('');
    setDistrictFilter('');
    setSourceFilter('');
    setCosTypeFilter('');
    setPage(1);
  };

  const openMotionSessionDetail = (sessionId: string | null) => {
    if (!sessionId) return;
    navigate(`/analytics/motions/sessions/${encodeURIComponent(sessionId)}`);
  };

  return (
    <AnalyticsLayout title="Motion Analytics">
      <section className="mb-8 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <KpiSurface
          label="Total Drafts"
          value={formatAnalyticsNumber(summary.total)}
          iconKey="motionsDrafted"
          loading={isLoading && !data}
        />
        <KpiSurface
          label="Success Rate"
          value={`${summary.successRate.toFixed(1)}%`}
          iconKey="activeCases"
          valueClass="text-app-success-text"
          loading={isLoading && !data}
        />
        <KpiSurface
          label="Avg Processing"
          value={formatMotionProcessing(summary.avgProcessingSeconds)}
          iconKey="pendingCases"
          valueClass="text-app-accent-text"
          loading={isLoading && !data}
        />
        <KpiSurface
          label="Completed"
          value={formatAnalyticsNumber(summary.completed)}
          iconKey="activeCases"
          valueClass="text-app-success-text"
          loading={isLoading && !data}
        />
      </section>

      <SectionCard
        className="mb-8"
        headerClassName="items-start gap-3"
        title={
          <div className="flex items-center gap-2">
            <FiFileText className="h-4 w-4 text-app-accent" />
            <span>Motions</span>
          </div>
        }
        action={
          <div className="ml-auto flex flex-col items-end gap-2">
            <div className="flex flex-wrap items-center justify-end gap-2">
              <label className="relative block min-w-[300px]">
                <FiSearch className="pointer-events-none absolute left-4 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-subtle" />
                <input
                  type="text"
                  value={searchInput}
                  onChange={(event) => setSearchInput(event.target.value)}
                  placeholder="Search case #, debtor, or session ID..."
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

              <div className="min-w-[190px]">
                <SelectDropdown
                  value={motionTypeFilter}
                  onChange={setMotionTypeFilter}
                  options={motionTypeOptions}
                  className="w-full [&>button]:h-[40px] [&>button]:py-0"
                />
              </div>

              <div className="min-w-[156px]">
                <SelectDropdown
                  value={categoryFilter}
                  onChange={setCategoryFilter}
                  options={MOTIONS_CATEGORY_OPTIONS}
                  className="w-full [&>button]:h-[40px] [&>button]:py-0"
                />
              </div>

              <div className="min-w-[156px]">
                <SelectDropdown
                  value={statusFilter}
                  onChange={setStatusFilter}
                  options={MOTIONS_STATUS_OPTIONS}
                  className="w-full [&>button]:h-[40px] [&>button]:py-0"
                />
              </div>

              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => setShowAdvancedFilters((current) => !current)}
                  className="inline-flex h-[40px] items-center gap-1 rounded-xl border border-border/80 bg-surface-muted px-3 text-sm font-semibold text-text transition hover:bg-surface"
                >
                  {advancedFilterCount ? `More filters (${advancedFilterCount})` : 'More filters'}
                  {showAdvancedFilters ? (
                    <FiChevronUp className="h-4 w-4" />
                  ) : (
                    <FiChevronDown className="h-4 w-4" />
                  )}
                </button>
              </div>
            </div>

            {showAdvancedFilters ? (
              <div className="inline-flex self-end flex-wrap items-center gap-2 rounded-xl border border-border bg-surface p-2.5">
                <div className="min-w-[156px]">
                  <SelectDropdown
                    value={districtFilter}
                    onChange={setDistrictFilter}
                    options={districtOptions}
                    className="w-full [&>button]:h-[40px] [&>button]:py-0"
                  />
                </div>

                <div className="min-w-[170px]">
                  <SelectDropdown
                    value={sourceFilter}
                    onChange={setSourceFilter}
                    options={MOTIONS_SOURCE_OPTIONS}
                    className="w-full [&>button]:h-[40px] [&>button]:py-0"
                  />
                </div>

                <div className="min-w-[170px]">
                  <SelectDropdown
                    value={cosTypeFilter}
                    onChange={setCosTypeFilter}
                    options={MOTIONS_COS_TYPE_OPTIONS}
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
            Failed to load motion analytics: {error.message}
          </div>
        ) : (
          <>
            <div className="mb-3 flex items-center justify-between gap-2">
              <p className="text-xs text-muted">
                {showMotionsTableSkeleton
                  ? 'Loading motions...'
                  : `Showing ${showingFrom}–${showingTo} of ${formatAnalyticsNumber(totalItems)} drafts`}
              </p>
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
              <table className="w-full min-w-[1520px] table-fixed border-collapse">
                <thead className="bg-surface-muted/75">
                  <tr>
                    <th className="w-[9%] px-4 py-3 text-left whitespace-nowrap">
                      <span className="inline-flex items-center whitespace-nowrap text-[11px] font-semibold uppercase tracking-[0.12em] text-muted">
                        Task ID
                      </span>
                    </th>
                    <th className="w-[9%] px-4 py-3 text-left whitespace-nowrap">
                      <span className="inline-flex items-center whitespace-nowrap text-[11px] font-semibold uppercase tracking-[0.12em] text-muted">
                        Case #
                      </span>
                    </th>
                    <th className="w-[14%] px-4 py-3 text-left whitespace-nowrap">
                      <span className="inline-flex items-center whitespace-nowrap text-[11px] font-semibold uppercase tracking-[0.12em] text-muted">
                        Debtor
                      </span>
                    </th>
                    <th className="w-[16%] px-4 py-3 text-left whitespace-nowrap">
                      <SortableHeader
                        label="Motion Type"
                        sortKey="motion_type"
                        activeSortKey={sortKey}
                        sortDir={sortDir}
                        onToggle={handleHeaderSortToggle}
                      />
                    </th>
                    <th className="w-[9%] px-4 py-3 text-left whitespace-nowrap">
                      <span className="inline-flex items-center whitespace-nowrap text-[11px] font-semibold uppercase tracking-[0.12em] text-muted">
                        Category
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
                    <th className="w-[11%] px-4 py-3 text-left whitespace-nowrap">
                      <span className="inline-flex items-center whitespace-nowrap text-[11px] font-semibold uppercase tracking-[0.12em] text-muted">
                        COS Type
                      </span>
                    </th>
                    <th className="w-[9%] px-4 py-3 text-left whitespace-nowrap">
                      <span className="inline-flex items-center whitespace-nowrap text-[11px] font-semibold uppercase tracking-[0.12em] text-muted">
                        Source
                      </span>
                    </th>
                    <th className="w-[9%] px-4 py-3 text-left whitespace-nowrap">
                      <span className="inline-flex items-center whitespace-nowrap text-[11px] font-semibold uppercase tracking-[0.12em] text-muted">
                        District
                      </span>
                    </th>
                    <th className="w-[13%] px-4 py-3 text-left whitespace-nowrap">
                      <SortableHeader
                        label="Created"
                        sortKey="created_at"
                        activeSortKey={sortKey}
                        sortDir={sortDir}
                        onToggle={handleHeaderSortToggle}
                      />
                    </th>
                    <th className="w-[7%] px-4 py-3 text-left whitespace-nowrap">
                      <SortableHeader
                        label="Process"
                        sortKey="processing"
                        activeSortKey={sortKey}
                        sortDir={sortDir}
                        onToggle={handleHeaderSortToggle}
                      />
                    </th>
                    <th className="w-[10%] px-4 py-3 text-left whitespace-nowrap">
                      <span className="inline-flex items-center whitespace-nowrap text-[11px] font-semibold uppercase tracking-[0.12em] text-muted">
                        Actor
                      </span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {showMotionsTableSkeleton ? (
                    Array.from({ length: 5 }).map((_, index) => (
                      <tr key={`motions-skeleton-${index}`} className="border-t border-border/70">
                        <td className="px-4 py-3">
                          <AnalyticsBodySkeleton className="h-5 w-20" />
                        </td>
                        <td className="px-4 py-3">
                          <AnalyticsBodySkeleton className="h-5 w-16" />
                        </td>
                        <td className="px-4 py-3">
                          <AnalyticsBodySkeleton className="h-5 w-28" />
                        </td>
                        <td className="px-4 py-3">
                          <AnalyticsBodySkeleton className="h-5 w-32" />
                        </td>
                        <td className="px-4 py-3">
                          <AnalyticsBodySkeleton className="h-5 w-20" />
                        </td>
                        <td className="px-4 py-3">
                          <AnalyticsBodySkeleton className="h-5 w-20" />
                        </td>
                        <td className="px-4 py-3">
                          <AnalyticsBodySkeleton className="h-5 w-24" />
                        </td>
                        <td className="px-4 py-3">
                          <AnalyticsBodySkeleton className="h-5 w-16" />
                        </td>
                        <td className="px-4 py-3">
                          <AnalyticsBodySkeleton className="h-5 w-16" />
                        </td>
                        <td className="px-4 py-3">
                          <AnalyticsBodySkeleton className="h-5 w-28" />
                        </td>
                        <td className="px-4 py-3">
                          <AnalyticsBodySkeleton className="h-5 w-14" />
                        </td>
                        <td className="px-4 py-3">
                          <AnalyticsBodySkeleton className="h-5 w-20" />
                        </td>
                      </tr>
                    ))
                  ) : rows.length ? (
                    rows.map((item: DashboardMotionAnalyticsItem) => (
                      <tr
                        key={item.task_id}
                        role={item.session_id ? 'link' : undefined}
                        aria-label={
                          item.session_id
                            ? `Open motion session details for ${item.case_number ?? item.session_id}`
                            : undefined
                        }
                        tabIndex={item.session_id ? 0 : -1}
                        onClick={() => openMotionSessionDetail(item.session_id)}
                        onKeyDown={(event) => {
                          if (!item.session_id) return;
                          if (event.key === 'Enter' || event.key === ' ') {
                            event.preventDefault();
                            openMotionSessionDetail(item.session_id);
                          }
                        }}
                        className={`border-t border-border/70 transition-colors ${
                          item.session_id
                            ? 'cursor-pointer hover:bg-activity-row-hover'
                            : 'hover:bg-activity-row-hover'
                        }`}
                      >
                        <td className="px-4 py-3 text-xs font-semibold text-text-secondary whitespace-nowrap">
                          <span className="block max-w-[132px] truncate" title={item.task_id}>
                            {item.task_id}
                          </span>
                        </td>
                        <td className="px-4 py-3 text-xs text-muted whitespace-nowrap">
                          {item.case_number ?? '--'}
                        </td>
                        <td className="px-4 py-3 text-xs text-text-secondary">
                          <p className="truncate" title={item.debtor_name ?? '--'}>
                            {item.debtor_name ?? '--'}
                          </p>
                        </td>
                        <td className="px-4 py-3">
                          <span className="inline-flex max-w-full truncate rounded-full border border-border bg-surface-muted px-2 py-0.5 text-[10px] font-semibold text-text-secondary">
                            {item.display_name || formatMotionsLabel(item.motion_type)}
                          </span>
                        </td>
                        <td className="px-4 py-3">
                          <span
                            className={`inline-flex whitespace-nowrap rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${getMotionCategoryBadgeClass(
                              item.category
                            )}`}
                          >
                            {formatMotionsLabel(item.category)}
                          </span>
                        </td>
                        <td className="px-4 py-3">
                          <span
                            className={`inline-flex whitespace-nowrap rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${getMotionStatusBadgeClass(
                              item.status
                            )}`}
                          >
                            {formatMotionsLabel(item.status)}
                          </span>
                        </td>
                        <td className="px-4 py-3">
                          <span
                            className={`inline-flex whitespace-nowrap rounded-full px-2 py-0.5 text-[10px] font-semibold ${getMotionCosBadgeClass(
                              item.cos_type
                            )}`}
                          >
                            {formatMotionCosType(item.cos_type)}
                          </span>
                        </td>
                        <td className="px-4 py-3 text-xs text-muted whitespace-nowrap">
                          {item.source ? formatMotionsLabel(item.source) : '--'}
                        </td>
                        <td className="px-4 py-3 text-xs text-muted whitespace-nowrap">
                          {item.district ? (
                            <span className="leading-4">
                              <span className="block text-text-secondary">
                                {getDistrictCode(item.district) ?? '--'}
                              </span>
                              <span className="block text-[11px] text-subtle">
                                {getDistrictName(item.district, 'short') ?? '--'}
                              </span>
                            </span>
                          ) : (
                            '--'
                          )}
                        </td>
                        <td className="px-4 py-3 text-xs text-muted whitespace-nowrap">
                          {formatMotionDateTime(item.created_at)}
                        </td>
                        <td className="px-4 py-3 text-xs font-medium text-text-secondary whitespace-nowrap">
                          {formatMotionProcessing(item.processing_seconds)}
                        </td>
                        <td className="px-4 py-3 text-xs text-muted whitespace-nowrap">
                          <p
                            className="truncate"
                            title={item.actor_name ?? item.actor_user_id ?? '--'}
                          >
                            {item.actor_name ?? item.actor_user_id ?? '--'}
                          </p>
                        </td>
                      </tr>
                    ))
                  ) : (
                    <tr>
                      <td colSpan={12} className="px-4 py-8 text-center text-sm text-muted">
                        No motions found for this filter set.
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
              pageSizeOptions={MOTIONS_PAGE_SIZE_OPTIONS}
              onPageChange={setPage}
              onPageSizeChange={setPageSize}
              className="mt-4"
              keyPrefix="motions-pagination"
            />
          </>
        )}
      </SectionCard>
    </AnalyticsLayout>
  );
};
