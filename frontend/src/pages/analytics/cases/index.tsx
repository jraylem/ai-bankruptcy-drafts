import React, { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { FiMapPin, FiSearch, FiUsers, FiX } from 'react-icons/fi';
import { SelectDropdown } from '@/components/common';
import { AnalyticsTablePaginationFooter } from '@/features/analytics/components/AnalyticsTablePaginationFooter';
import { AnalyticsLayout } from '@/features/analytics/components/shared';
import { AnalyticsBodySkeleton } from '@/features/analytics/components/AnalyticsSkeleton';
import { KpiSurface } from '@/features/analytics/components/KpiSurface';
import { SectionCard } from '@/features/analytics/components/SectionCard';
import { SortableHeader } from '@/features/analytics/components/SortableHeader';
import { useDashboardAnalyticsCases } from '@/features/analytics/hooks/useDashboardAnalyticsCases';
import { useAnalyticsFiltersStore } from '@/features/analytics/stores/useAnalyticsFiltersStore';
import type {
  DashboardCaseAnalyticsItem,
  DashboardCaseSource,
  DashboardCasesAnalyticsQuery,
} from '@/features/analytics/types/dashboard.types';
import {
  CASE_SOURCE_OPTIONS,
  CASE_STATUS_OPTIONS,
  CASES_PAGE_SIZE_OPTIONS,
  type CasesTableSortKey,
  formatCaseLabel,
  formatCaseRelativeActivity,
  getCaseBucketBadgeClass,
  getCaseStatusBadgeClass,
  resolveCasesServerSortBy,
} from '@/features/analytics/utils/casesList.helpers';
import {
  DISTRICT_FILTER_KEYS,
  formatDistrictLabel,
  getDistrictCode,
  getDistrictName,
} from '@/features/analytics/utils/districtLabels';
import { formatAnalyticsNumber } from '@/features/analytics/utils/dashboard.mappers';
type SortDirection = 'asc' | 'desc';

export const AnalyticsCasesPage: React.FC = () => {
  const navigate = useNavigate();
  const { rangePreset } = useAnalyticsFiltersStore();
  const [searchInput, setSearchInput] = useState('');
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [districtFilter, setDistrictFilter] = useState('');
  const [sourceFilter, setSourceFilter] = useState('');
  const [pageSize, setPageSize] = useState<number>(10);
  const [page, setPage] = useState<number>(1);
  const [sortKey, setSortKey] = useState<CasesTableSortKey>('last_activity');
  const [sortDir, setSortDir] = useState<SortDirection>('desc');
  const trimmedSearchInput = useMemo(() => searchInput.trim(), [searchInput]);
  const hasActiveFilters = Boolean(
    searchInput.trim() || statusFilter || districtFilter || sourceFilter
  );

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
    statusFilter,
    districtFilter,
    sourceFilter,
    pageSize,
    sortKey,
    sortDir,
  ]);

  const serverSortBy = resolveCasesServerSortBy(sortKey);

  const listQuery = useMemo<DashboardCasesAnalyticsQuery>(
    () => ({
      page,
      page_size: pageSize,
      sort_by: serverSortBy,
      sort_dir: sortDir,
      ...(searchQuery ? { search: searchQuery } : {}),
      ...(statusFilter ? { status: statusFilter } : {}),
      ...(districtFilter ? { district: districtFilter } : {}),
      ...(sourceFilter ? { source: sourceFilter as DashboardCaseSource } : {}),
    }),
    [districtFilter, page, pageSize, searchQuery, serverSortBy, sortDir, sourceFilter, statusFilter]
  );

  const { data, isLoading, isFetching, error } = useDashboardAnalyticsCases(listQuery);
  const totalItems = data?.pagination.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(totalItems / pageSize));

  useEffect(() => {
    if (page > totalPages) {
      setPage(totalPages);
    }
  }, [page, totalPages]);

  const summary = {
    total: data?.kpis.total ?? 0,
    active: data?.kpis.active.sum ?? 0,
    pending: data?.kpis.pending ?? 0,
    inactive: data?.kpis.inactive.sum ?? 0,
  };

  const districtOptions = useMemo(() => {
    const byDistrict = data?.kpis.by_district;
    if (!byDistrict) {
      return [
        { label: 'All districts', value: '' },
        ...DISTRICT_FILTER_KEYS.map((district) => ({
          label: formatDistrictLabel(district),
          value: district,
        })),
      ];
    }

    const knownDistricts: Array<{ key: string; total: number }> = [
      { key: 'flnb', total: byDistrict.flnb },
      { key: 'flmb', total: byDistrict.flmb },
      { key: 'flsb', total: byDistrict.flsb },
      { key: 'pawb', total: byDistrict.pawb },
      { key: 'other', total: byDistrict.other },
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

  const rows = data?.cases ?? [];

  const showingFrom = totalItems === 0 ? 0 : (page - 1) * pageSize + 1;
  const showingTo = Math.min(page * pageSize, totalItems);
  const showCasesTableSkeleton = isLoading || isFetching;

  const handleHeaderSortToggle = (nextSortKey: CasesTableSortKey) => {
    setSortDir((current) => {
      if (sortKey === nextSortKey) {
        return current === 'asc' ? 'desc' : 'asc';
      }

      return 'desc';
    });
    setSortKey(nextSortKey);
  };

  const openCaseDetail = (sessionId: string) => {
    navigate(`/analytics/cases/${encodeURIComponent(sessionId)}`);
  };

  const handleClearFilters = () => {
    setSearchInput('');
    setSearchQuery('');
    setStatusFilter('');
    setDistrictFilter('');
    setSourceFilter('');
    setPage(1);
  };

  return (
    <AnalyticsLayout title="Case Analytics">
      <section className="mb-8 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <KpiSurface
          label="Total Cases"
          value={formatAnalyticsNumber(summary.total)}
          iconKey="totalCases"
          loading={isLoading && !data}
        />
        <KpiSurface
          label="Active Cases"
          value={formatAnalyticsNumber(summary.active)}
          iconKey="activeCases"
          valueClass="text-app-success-text"
          loading={isLoading && !data}
        />
        <KpiSurface
          label="Pending Cases"
          value={formatAnalyticsNumber(summary.pending)}
          iconKey="pendingCases"
          valueClass="text-app-warning-text"
          loading={isLoading && !data}
        />
        <KpiSurface
          label="Inactive Cases"
          value={formatAnalyticsNumber(summary.inactive)}
          iconKey="totalCases"
          valueClass="text-muted"
          loading={isLoading && !data}
        />
      </section>

      <SectionCard
        className="mb-8"
        title={
          <div className="flex items-center gap-2">
            <FiUsers className="h-4 w-4 text-app-accent" />
            <span>Cases</span>
          </div>
        }
        action={
          <div className="flex flex-wrap items-center gap-2">
            <label className="relative block min-w-[380px]">
              <FiSearch className="pointer-events-none absolute left-4 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-subtle" />
              <input
                type="text"
                value={searchInput}
                onChange={(event) => setSearchInput(event.target.value)}
                placeholder="Search case #, debtor, or session..."
                className="h-[40px] w-full rounded-xl border-0 bg-surface-muted pl-10 pr-11 text-sm text-text-secondary outline-none transition focus:ring-2 focus:ring-option-selected-ring placeholder:text-subtle"
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

            <div className="min-w-[156px]">
              <SelectDropdown
                value={statusFilter}
                onChange={setStatusFilter}
                options={CASE_STATUS_OPTIONS}
                className="w-full [&>button]:h-[40px] [&>button]:py-0"
              />
            </div>

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
                options={CASE_SOURCE_OPTIONS}
                className="w-full [&>button]:h-[40px] [&>button]:py-0"
              />
            </div>
          </div>
        }
      >
        {error ? (
          <div className="rounded-2xl border border-app-danger-text/30 bg-app-danger-soft px-4 py-3 text-sm text-app-danger-text">
            Failed to load cases analytics: {error.message}
          </div>
        ) : (
          <>
            <div className="mb-3 flex items-center justify-between gap-2">
              {showCasesTableSkeleton ? (
                <AnalyticsBodySkeleton className="h-4 max-w-44" />
              ) : (
                <p className="text-xs text-muted">
                  Showing {showingFrom}–{showingTo} of {formatAnalyticsNumber(totalItems)} cases
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
              <table className="w-full min-w-[1080px] table-fixed border-collapse">
                <thead className="bg-surface-muted/75">
                  <tr>
                    <th className="w-[24%] px-4 py-3 text-left whitespace-nowrap">
                      <SortableHeader
                        label="Case"
                        sortKey="case"
                        activeSortKey={sortKey}
                        sortDir={sortDir}
                        onToggle={handleHeaderSortToggle}
                      />
                    </th>
                    <th className="w-[10%] px-4 py-3 text-left whitespace-nowrap">
                      <SortableHeader
                        label="District"
                        sortKey="district"
                        activeSortKey={sortKey}
                        sortDir={sortDir}
                        onToggle={handleHeaderSortToggle}
                      />
                    </th>
                    <th className="w-[12%] px-4 py-3 text-left whitespace-nowrap">
                      <SortableHeader
                        label="Status"
                        sortKey="status"
                        activeSortKey={sortKey}
                        sortDir={sortDir}
                        onToggle={handleHeaderSortToggle}
                      />
                    </th>
                    <th className="w-[10%] px-4 py-3 text-left whitespace-nowrap">
                      <SortableHeader
                        label="Bucket"
                        sortKey="bucket"
                        activeSortKey={sortKey}
                        sortDir={sortDir}
                        onToggle={handleHeaderSortToggle}
                      />
                    </th>
                    <th className="w-[10%] px-4 py-3 text-left whitespace-nowrap">
                      <SortableHeader
                        label="Source"
                        sortKey="source"
                        activeSortKey={sortKey}
                        sortDir={sortDir}
                        onToggle={handleHeaderSortToggle}
                      />
                    </th>
                    <th className="w-[12%] px-4 py-3 text-left whitespace-nowrap">
                      <SortableHeader
                        label="Last Activity"
                        sortKey="last_activity"
                        activeSortKey={sortKey}
                        sortDir={sortDir}
                        onToggle={handleHeaderSortToggle}
                      />
                    </th>
                    <th className="w-[12%] px-4 py-3 text-left whitespace-nowrap">
                      <SortableHeader
                        label="Motions"
                        sortKey="motions"
                        activeSortKey={sortKey}
                        sortDir={sortDir}
                        onToggle={handleHeaderSortToggle}
                      />
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {showCasesTableSkeleton ? (
                    Array.from({ length: 5 }).map((_, index) => (
                      <tr key={`cases-skeleton-${index}`} className="border-t border-border/70">
                        <td className="px-4 py-3">
                          <AnalyticsBodySkeleton className="h-10 w-full" />
                        </td>
                        <td className="px-4 py-3">
                          <AnalyticsBodySkeleton className="h-5 w-20" />
                        </td>
                        <td className="px-4 py-3">
                          <AnalyticsBodySkeleton className="h-5 w-16" />
                        </td>
                        <td className="px-4 py-3">
                          <AnalyticsBodySkeleton className="h-5 w-16" />
                        </td>
                        <td className="px-4 py-3">
                          <AnalyticsBodySkeleton className="h-5 w-16" />
                        </td>
                        <td className="px-4 py-3">
                          <AnalyticsBodySkeleton className="h-5 w-20" />
                        </td>
                        <td className="px-4 py-3">
                          <AnalyticsBodySkeleton className="h-5 w-12" />
                        </td>
                      </tr>
                    ))
                  ) : rows.length ? (
                    rows.map((caseItem: DashboardCaseAnalyticsItem) => (
                      <tr
                        key={caseItem.session_id}
                        role="link"
                        aria-label={`Open case details for ${caseItem.case_number || caseItem.session_id}`}
                        tabIndex={0}
                        onClick={() => openCaseDetail(caseItem.session_id)}
                        onKeyDown={(event) => {
                          if (event.key === 'Enter' || event.key === ' ') {
                            event.preventDefault();
                            openCaseDetail(caseItem.session_id);
                          }
                        }}
                        className="cursor-pointer border-t border-border/70 transition-colors hover:bg-activity-row-hover"
                      >
                        <td className="px-4 py-3">
                          <div className="min-w-0">
                            <p className="truncate text-sm font-semibold text-text">
                              {caseItem.case_number || caseItem.session_id}
                            </p>
                            <p className="truncate text-xs text-muted">
                              {caseItem.debtor_name || 'Unknown debtor'}
                            </p>
                          </div>
                        </td>
                        <td className="px-4 py-3 text-xs text-muted">
                          <span className="inline-flex items-start gap-1.5">
                            <FiMapPin className="h-3 w-3" />
                            {caseItem.district ? (
                              <span className="leading-4">
                                <span className="block text-text-secondary">
                                  {getDistrictCode(caseItem.district) ?? '--'}
                                </span>
                                <span className="block text-[11px] text-subtle">
                                  {getDistrictName(caseItem.district, 'short') ?? '--'}
                                </span>
                              </span>
                            ) : (
                              '--'
                            )}
                          </span>
                        </td>
                        <td className="px-4 py-3">
                          <span
                            className={`whitespace-nowrap rounded-full px-2 py-0.5 text-[10px] font-semibold ${getCaseStatusBadgeClass(
                              caseItem.petition_status
                            )}`}
                          >
                            {formatCaseLabel(caseItem.petition_status || 'unknown')}
                          </span>
                        </td>
                        <td className="px-4 py-3">
                          <span
                            className={`whitespace-nowrap rounded-full px-2 py-0.5 text-[10px] font-semibold ${getCaseBucketBadgeClass(
                              caseItem.bucket
                            )}`}
                          >
                            {formatCaseLabel(caseItem.bucket)}
                          </span>
                        </td>
                        <td className="px-4 py-3 text-xs text-muted whitespace-nowrap">
                          {caseItem.source ? formatCaseLabel(caseItem.source) : '--'}
                        </td>
                        <td className="px-4 py-3 text-xs text-muted whitespace-nowrap">
                          {formatCaseRelativeActivity(caseItem.last_activity_at)}
                        </td>
                        <td className="px-4 py-3 text-sm font-semibold text-text whitespace-nowrap">
                          {formatAnalyticsNumber(caseItem.motions_count)}
                        </td>
                      </tr>
                    ))
                  ) : (
                    <tr>
                      <td colSpan={7} className="px-4 py-8 text-center text-sm text-muted">
                        No cases found for this filter set.
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
              pageSizeOptions={CASES_PAGE_SIZE_OPTIONS}
              onPageChange={setPage}
              onPageSizeChange={setPageSize}
              className="mt-4"
              keyPrefix="cases-pagination"
            />
          </>
        )}
      </SectionCard>
    </AnalyticsLayout>
  );
};
