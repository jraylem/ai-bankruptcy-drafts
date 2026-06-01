import type { DashboardCasesAnalyticsSortBy } from '@/features/analytics/types/dashboard.types';
import { formatRelativeActivityTime } from './activityFeed.helpers';
import { ANALYTICS_TABLE_PAGE_SIZE_OPTIONS, toAnalyticsTitleCase } from './common.helpers';

export type CasesTableSortKey =
  | 'case'
  | 'district'
  | 'status'
  | 'bucket'
  | 'source'
  | 'last_activity'
  | 'motions';

export const CASES_PAGE_SIZE_OPTIONS = ANALYTICS_TABLE_PAGE_SIZE_OPTIONS;

export const CASE_SOURCE_OPTIONS = [
  { label: 'All sources', value: '' },
  { label: 'Manual', value: 'manual' },
  { label: 'ECF', value: 'ecf' },
  { label: 'Google Drive', value: 'gdrive' },
  { label: 'CourtDrive', value: 'courtdrive' },
];

export const CASE_STATUS_OPTIONS = [
  { label: 'All statuses', value: '' },
  { label: 'Working', value: 'working' },
  { label: 'Accepted', value: 'accepted' },
  { label: 'Pending Acceptance', value: 'pending_acceptance' },
  { label: 'Denied', value: 'denied' },
  { label: 'Archived', value: 'archived' },
  { label: 'Deleted', value: 'deleted' },
];

export const formatCaseLabel = toAnalyticsTitleCase;

export const formatCaseRelativeActivity = (value: string | null) => {
  if (!value) return 'No activity';
  return formatRelativeActivityTime(value);
};

export const getCaseStatusBadgeClass = (status: string | null) => {
  if (!status) return 'bg-surface-muted text-muted';
  if (['working', 'accepted'].includes(status)) return 'bg-app-success-soft text-app-success-text';
  if (status === 'pending_acceptance') return 'bg-app-warning-soft text-app-warning-text';
  if (status === 'denied' || status === 'deleted') return 'bg-app-danger-soft text-app-danger-text';
  if (status === 'archived') return 'bg-surface-muted text-muted';
  return 'bg-app-accent-soft text-app-accent-text';
};

export const getCaseBucketBadgeClass = (bucket: string) => {
  if (bucket === 'active') return 'bg-app-success-soft text-app-success-text';
  if (bucket === 'pending') return 'bg-app-warning-soft text-app-warning-text';
  if (bucket === 'inactive') return 'bg-surface-muted text-muted';
  return 'bg-app-accent-soft text-app-accent-text';
};

export const resolveCasesServerSortBy = (sortKey: CasesTableSortKey): DashboardCasesAnalyticsSortBy => {
  if (sortKey === 'case') return 'debtor_name';
  if (sortKey === 'district') return 'district';
  if (sortKey === 'status') return 'status';
  if (sortKey === 'bucket') return 'bucket';
  if (sortKey === 'source') return 'source';
  if (sortKey === 'last_activity') return 'last_activity_at';
  if (sortKey === 'motions') return 'motions_count';
  return 'debtor_name';
};
