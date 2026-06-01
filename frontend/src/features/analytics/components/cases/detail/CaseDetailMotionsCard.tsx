import React from 'react';
import { FiFileText, FiSearch, FiX } from 'react-icons/fi';
import { SelectDropdown } from '@/components/common';
import { AnalyticsTablePaginationFooter } from '@/features/analytics/components/AnalyticsTablePaginationFooter';
import { SectionCard } from '@/features/analytics/components/SectionCard';
import {
  CASE_DETAIL_MOTION_STATUS_OPTIONS,
  CASE_DETAIL_PAGE_SIZE_OPTIONS,
  formatCaseDetailDateTime,
  formatCaseDetailDuration,
  formatCaseDetailLabel,
  getCaseMotionStatusBadgeClass,
} from '@/features/analytics/utils/caseDetail.helpers';
import { formatAnalyticsNumber } from '@/features/analytics/utils/dashboard.mappers';
import type { CaseDetailMotionsCardProps } from './types';

export const CaseDetailMotionsCard: React.FC<CaseDetailMotionsCardProps> = ({ motions }) => {
  return (
    <SectionCard
      title={
        <div className="flex items-center gap-2">
          <FiFileText className="h-4 w-4 text-app-accent" />
          <span>Motions</span>
        </div>
      }
      action={
        <div className="flex flex-wrap items-center gap-2">
          <label className="relative block min-w-[300px]">
            <FiSearch className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-subtle" />
            <input
              type="text"
              value={motions.searchInput}
              onChange={(event) => motions.setSearchInput(event.target.value)}
              placeholder="Search motion type, case name, or case number..."
              className="h-[40px] w-full rounded-xl border-0 bg-surface-muted pl-9 pr-9 text-sm text-text-secondary outline-none transition focus:ring-2 focus:ring-option-selected-ring placeholder:text-subtle"
            />
            {motions.searchInput ? (
              <button
                type="button"
                onClick={motions.clearSearch}
                aria-label="Clear motion search"
                className="absolute right-2.5 top-1/2 -translate-y-1/2 text-subtle transition hover:text-text-secondary"
              >
                <FiX className="h-3.5 w-3.5" />
              </button>
            ) : null}
          </label>
          <div className="min-w-[160px]">
            <SelectDropdown
              value={motions.statusFilter}
              onChange={motions.setStatusFilter}
              options={CASE_DETAIL_MOTION_STATUS_OPTIONS}
              className="w-full [&>button]:h-[40px] [&>button]:py-0"
            />
          </div>
          {motions.hasFilters ? (
            <button
              type="button"
              onClick={motions.clearFilters}
              className="text-xs font-medium text-app-accent-text transition hover:underline"
            >
              Clear filters
            </button>
          ) : null}
        </div>
      }
    >
      {motions.totalItems ? (
        <>
          <div className="mb-3 flex items-center justify-between gap-2">
            <p className="text-xs text-muted">
              Showing {motions.showingFrom}–{motions.showingTo} of{' '}
              {formatAnalyticsNumber(motions.totalItems)} motions
            </p>
          </div>

          <div className="overflow-x-auto rounded-xl border border-border/70">

            <table className="min-w-full table-fixed border-collapse">
              <thead className="bg-surface-muted/75">
                <tr>
                  <th className="whitespace-nowrap px-3 py-2 text-left text-[10px] font-semibold uppercase tracking-[0.12em] text-muted">
                    Type
                  </th>
                  <th className="whitespace-nowrap px-3 py-2 text-left text-[10px] font-semibold uppercase tracking-[0.12em] text-muted">
                    Status
                  </th>
                  <th className="whitespace-nowrap px-3 py-2 text-left text-[10px] font-semibold uppercase tracking-[0.12em] text-muted">
                    Created
                  </th>
                  <th className="whitespace-nowrap px-3 py-2 text-left text-[10px] font-semibold uppercase tracking-[0.12em] text-muted">
                    Duration
                  </th>
                </tr>
              </thead>
              <tbody>
                {motions.rows.length ? (
                  motions.rows.map((motion) => (
                    <tr key={motion.task_id} className="border-t border-border/70">
                      <td className="px-3 py-2 text-xs text-text-secondary">
                        {formatCaseDetailLabel(motion.motion_type)}
                      </td>
                      <td className="px-3 py-2">
                        <span
                          className={`whitespace-nowrap rounded-full px-2 py-0.5 text-[10px] font-semibold ${getCaseMotionStatusBadgeClass(
                            motion.status
                          )}`}
                        >
                          {formatCaseDetailLabel(motion.status)}
                        </span>
                      </td>
                      <td className="px-3 py-2 text-[11px] text-muted">
                        {formatCaseDetailDateTime(motion.created_at)}
                      </td>
                      <td className="px-3 py-2 text-[11px] text-muted">
                        {formatCaseDetailDuration(motion.processing_seconds)}
                      </td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan={4} className="px-3 py-6 text-center text-xs text-subtle">
                      No motions found for this filter set.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>

            <AnalyticsTablePaginationFooter
              page={motions.currentPage}
              totalPages={motions.totalPages}
              pageSize={motions.currentPageSize}
              pageSizeOptions={CASE_DETAIL_PAGE_SIZE_OPTIONS}
              onPageChange={motions.setPage}
              onPageSizeChange={motions.setPageSize}
              className="border-t border-border/70 bg-surface px-3"
              keyPrefix="motions-pagination"
            />
          </div>
        </>
      ) : (
        <p className="text-xs text-subtle">No motion history found.</p>
      )}
    </SectionCard>
  );
};
