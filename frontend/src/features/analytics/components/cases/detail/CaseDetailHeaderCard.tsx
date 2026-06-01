import React from 'react';
import { FiExternalLink, FiMapPin } from 'react-icons/fi';
import { SectionCard } from '@/features/analytics/components/SectionCard';
import {
  formatCaseDetailDateTime,
  formatCaseDetailLabel,
  formatCaseDetailRelative,
  getCaseDetailBucketBadgeClass,
  getCaseDetailStatusBadgeClass,
} from '@/features/analytics/utils/caseDetail.helpers';
import { formatDistrictLabel } from '@/features/analytics/utils/districtLabels';
import { formatAnalyticsNumber } from '@/features/analytics/utils/dashboard.mappers';
import type { CaseDetailHeaderCardProps } from './types';

export const CaseDetailHeaderCard: React.FC<CaseDetailHeaderCardProps> = ({
  canOpenDashboard,
  detail,
  onOpenDashboard,
}) => {
  return (
    <SectionCard
      className="mb-6"
      title={
        <div className="min-w-0">
          <h1 className="truncate text-2xl font-semibold text-text">
            {detail.case_number || detail.session_id}
          </h1>
          <p className="mt-1 truncate text-sm text-muted">{detail.debtor_name || 'Unknown debtor'}</p>
        </div>
      }
      action={
        <div className="flex flex-wrap items-center gap-2">
          <span
            className={`rounded-full px-2.5 py-1 text-xs font-semibold ${getCaseDetailStatusBadgeClass(
              detail.petition_status
            )}`}
          >
            {formatCaseDetailLabel(detail.petition_status || 'unknown')}
          </span>
          <span
            className={`rounded-full px-2.5 py-1 text-xs font-semibold ${getCaseDetailBucketBadgeClass(
              detail.bucket
            )}`}
          >
            {formatCaseDetailLabel(detail.bucket)}
          </span>
          {detail.source ? (
            <span className="rounded-full bg-surface-muted px-2.5 py-1 text-xs font-semibold text-muted">
              {formatCaseDetailLabel(detail.source)}
            </span>
          ) : null}
          {detail.district ? (
            <span className="inline-flex items-center gap-1.5 rounded-full bg-surface-muted px-2.5 py-1 text-xs font-semibold text-muted">
              <FiMapPin className="h-3 w-3" />
              {formatDistrictLabel(detail.district)}
            </span>
          ) : null}
          <button
            type="button"
            onClick={onOpenDashboard}
            disabled={!canOpenDashboard}
            className="ml-2 inline-flex items-center gap-2 rounded-xl border border-border px-3 py-2 text-xs font-semibold text-text-secondary transition hover:bg-surface-muted disabled:cursor-not-allowed disabled:opacity-50"
          >
            <FiExternalLink className="h-3.5 w-3.5" />
            Open In Dashboard
          </button>
        </div>
      }
    >
      <div className="grid gap-3 sm:grid-cols-4">
        <div className="rounded-xl border border-border bg-surface-muted/40 px-3 py-2">
          <p className="text-[10px] uppercase tracking-[0.12em] text-subtle">Created</p>
          <p className="mt-1 text-xs font-medium text-text-secondary">
            {formatCaseDetailDateTime(detail.created_at)}
          </p>
        </div>
        <div className="rounded-xl border border-border bg-surface-muted/40 px-3 py-2">
          <p className="text-[10px] uppercase tracking-[0.12em] text-subtle">Last Activity</p>
          <p className="mt-1 text-xs font-medium text-text-secondary">
            {formatCaseDetailRelative(detail.last_activity_at)}
          </p>
        </div>
        <div className="rounded-xl border border-border bg-surface-muted/40 px-3 py-2">
          <p className="text-[10px] uppercase tracking-[0.12em] text-subtle">Motions</p>
          <p className="mt-1 text-xs font-semibold text-text">
            {formatAnalyticsNumber(detail.motions_count)}
          </p>
        </div>
        <div className="rounded-xl border border-border bg-surface-muted/40 px-3 py-2">
          <p className="text-[10px] uppercase tracking-[0.12em] text-subtle">Session ID</p>
          <p className="mt-1 truncate text-xs font-medium text-text-secondary">{detail.session_id}</p>
        </div>
      </div>
    </SectionCard>
  );
};
