import type { DashboardCaseDocument } from '@/features/analytics/types/dashboard.types';
import { formatRelativeActivityTime } from './activityFeed.helpers';
import { ANALYTICS_TABLE_PAGE_SIZE_OPTIONS, toAnalyticsTitleCase } from './common.helpers';

export type CaseDetailDocumentActionMode = 'view' | 'download';

export const CASE_DETAIL_PAGE_SIZE_OPTIONS = ANALYTICS_TABLE_PAGE_SIZE_OPTIONS;

export const CASE_DETAIL_MOTION_STATUS_OPTIONS = [
  { label: 'All statuses', value: '' },
  { label: 'Pending', value: 'pending' },
  { label: 'Completed', value: 'completed' },
  { label: 'Failed', value: 'failed' },
  { label: 'Cancelled', value: 'cancelled' },
];

export const formatCaseDetailLabel = toAnalyticsTitleCase;

export const formatCaseDetailDateTime = (value: string | null) => {
  if (!value) return '--';

  return new Date(value).toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  });
};

export const formatCaseDetailRelative = (value: string | null) => {
  if (!value) return 'No activity';
  return formatRelativeActivityTime(value);
};

export const formatCaseDetailDuration = (seconds: number | null) => {
  if (seconds === null || !Number.isFinite(seconds)) return '--';
  if (seconds < 60) return `${Math.round(seconds)}s`;

  const mins = Math.floor(seconds / 60);
  const remainder = Math.round(seconds % 60);
  return `${mins}m ${remainder}s`;
};

export const getCaseDetailStatusBadgeClass = (status: string | null) => {
  if (!status) return 'border border-border bg-surface-muted text-muted';
  if (['working', 'accepted'].includes(status)) {
    return 'border border-border bg-app-success-soft text-app-success-text';
  }
  if (status === 'pending_acceptance') {
    return 'border border-border bg-app-warning-soft text-app-warning-text';
  }
  if (status === 'denied' || status === 'deleted') {
    return 'border border-border bg-app-danger-soft text-app-danger-text';
  }
  if (status === 'archived') return 'border border-border bg-surface-muted text-text-secondary';
  return 'border border-border bg-app-accent-soft text-app-accent-text';
};

export const getCaseDetailBucketBadgeClass = (bucket: string) => {
  if (bucket === 'active') return 'border border-border bg-app-success-soft text-app-success-text';
  if (bucket === 'pending') return 'border border-border bg-app-warning-soft text-app-warning-text';
  if (bucket === 'inactive') return 'border border-border bg-surface-muted text-muted';
  return 'border border-border bg-app-accent-soft text-app-accent-text';
};

export const getCaseMotionStatusBadgeClass = (status: string) => {
  if (status === 'completed') return 'border border-border bg-app-success-soft text-app-success-text';
  if (status === 'pending') return 'border border-border bg-app-warning-soft text-app-warning-text';
  if (status === 'failed' || status === 'cancelled') {
    return 'border border-border bg-app-danger-soft text-app-danger-text';
  }
  return 'border border-border bg-surface-muted text-muted';
};

export const buildCaseDetailDocumentKey = (
  document: DashboardCaseDocument,
  mode?: CaseDetailDocumentActionMode
) => `${document.filename}-${document.uploaded_at}${mode ? `-${mode}` : ''}`;
