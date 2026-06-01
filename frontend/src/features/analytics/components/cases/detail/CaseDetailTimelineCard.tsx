import React from 'react';
import { FiActivity } from 'react-icons/fi';
import { AnalyticsTablePaginationFooter } from '@/features/analytics/components/AnalyticsTablePaginationFooter';
import { SectionCard } from '@/features/analytics/components/SectionCard';
import {
  CASE_DETAIL_PAGE_SIZE_OPTIONS,
  formatCaseDetailLabel,
  formatCaseDetailRelative,
} from '@/features/analytics/utils/caseDetail.helpers';
import { formatAnalyticsNumber } from '@/features/analytics/utils/dashboard.mappers';
import type { CaseDetailTimelineCardProps } from './types';

export const CaseDetailTimelineCard: React.FC<CaseDetailTimelineCardProps> = ({ timeline }) => {
  return (
    <SectionCard
      title={
        <div className="flex items-center gap-2">
          <FiActivity className="h-4 w-4 text-app-accent" />
          <span>Timeline</span>
        </div>
      }
    >
      {timeline.totalItems ? (
        <div className="space-y-2">
          <div className="mb-3 flex items-center justify-between gap-2">
            <p className="text-xs text-muted">
              Showing {timeline.showingFrom}–{timeline.showingTo} of{' '}
              {formatAnalyticsNumber(timeline.totalItems)} events
            </p>
          </div>

          {timeline.items.map((event, index) => (
            <div
              key={`${event.event}-${event.at}-${index}`}
              className="rounded-xl border border-border/70 bg-surface-muted/50 px-3 py-2.5"
            >
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="text-xs font-semibold text-text">{formatCaseDetailLabel(event.event)}</span>
                <span className="text-[11px] text-subtle">{formatCaseDetailRelative(event.at)}</span>
              </div>
              {event.detail ? <p className="mt-1.5 text-xs text-muted">{event.detail}</p> : null}
              {event.actor ? (
                <p className="mt-1 text-[11px] text-subtle">{event.actor.name || event.actor.user_id}</p>
              ) : null}
            </div>
          ))}

          <AnalyticsTablePaginationFooter
            page={timeline.currentPage}
            totalPages={timeline.totalPages}
            pageSize={timeline.currentPageSize}
            pageSizeOptions={CASE_DETAIL_PAGE_SIZE_OPTIONS}
            onPageChange={timeline.setPage}
            onPageSizeChange={timeline.setPageSize}
            className="mt-3"
            keyPrefix="timeline-pagination"
          />
        </div>
      ) : (
        <p className="text-xs text-subtle">No timeline events found.</p>
      )}
    </SectionCard>
  );
};
