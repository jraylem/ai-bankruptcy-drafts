import type {
  UserDetailActivityStatusFilter,
  UserDetailActivityStatus,
  UserDetailSessionSource,
  UserDetailSessionStatus,
} from '@/features/analytics/types';
import {
  ANALYTICS_TABLE_PAGE_SIZE_OPTIONS,
  downloadAnalyticsExportBlob,
  sanitizeAnalyticsFilenameToken,
  toAnalyticsTitleCase,
} from './common.helpers';

export const SOURCES: UserDetailSessionSource[] = ['manual', 'ecf', 'gdrive', 'courtdrive'];

export const SESSION_STATUSES: UserDetailSessionStatus[] = [
  'working',
  'accepted',
  'pending_acceptance',
  'archived',
];

export const ACTIVITY_ACTIONS = [
  'draft_motion',
  'generate_document',
  'download_motion',
  'upload_pdf',
  'accept_case',
] as const;

export const ACTIVITY_STATUSES: UserDetailActivityStatusFilter[] = ['completed', 'pending', 'failed'];

export const DETAIL_PAGE_SIZE_OPTIONS = ANALYTICS_TABLE_PAGE_SIZE_OPTIONS;

export const toTitleCase = toAnalyticsTitleCase;

export const SESSION_SOURCE_OPTIONS = [
  { label: 'All sources', value: '' },
  ...SOURCES.map((source) => ({ label: toTitleCase(source), value: source })),
];

export const SESSION_STATUS_OPTIONS = [
  { label: 'All statuses', value: '' },
  ...SESSION_STATUSES.map((status) => ({ label: toTitleCase(status), value: status })),
];

export const ACTIVITY_ACTION_OPTIONS = [
  { label: 'All actions', value: '' },
  ...ACTIVITY_ACTIONS.map((action) => ({ label: toTitleCase(action), value: action })),
];

export const ACTIVITY_STATUS_OPTIONS = [
  { label: 'All statuses', value: '' },
  ...ACTIVITY_STATUSES.map((status) => ({ label: toTitleCase(status), value: status })),
];

export const formatDateTime = (value: string | null) =>
  value
    ? new Date(value).toLocaleString('en-US', {
        month: 'short',
        day: 'numeric',
        year: 'numeric',
        hour: 'numeric',
        minute: '2-digit',
      })
    : '--';

export const formatDuration = (seconds: number | null) => {
  if (seconds === null || !Number.isFinite(seconds)) return '--';
  if (seconds < 60) return `${Math.round(seconds)}s`;
  const mins = Math.floor(seconds / 60);
  const remainder = Math.round(seconds % 60);
  return `${mins}m ${remainder}s`;
};

export const formatDurationMs = (durationMs: number) => {
  if (durationMs < 1000) return `${Math.round(durationMs)}ms`;
  const seconds = durationMs / 1000;
  if (seconds < 10) return `${seconds.toFixed(1)}s`;
  return `${Math.round(seconds)}s`;
};

export const compareText = (left: string, right: string) =>
  left.localeCompare(right, undefined, {
    numeric: true,
    sensitivity: 'base',
  });

export const getStatusBadgeClass = (status: UserDetailActivityStatus) => {
  if (status === 'completed') return 'border-border bg-app-success-soft text-app-success-text';
  if (status === 'pending') return 'border-border bg-app-warning-soft text-app-warning-text';
  if (status === 'failed' || status === 'denied') return 'border-border bg-app-danger-soft text-app-danger-text';
  if (status === 'accepted' || status === 'success') {
    return 'border-border bg-app-success-soft text-app-success-text';
  }
  if (status === 'archived') return 'border-border bg-surface-muted text-muted';
  return 'border-border bg-app-danger-soft text-app-danger-text';
};

export const getSessionStatusBadgeClass = (status: UserDetailSessionStatus) => {
  if (status === 'accepted' || status === 'working') {
    return 'border-border bg-app-success-soft text-app-success-text';
  }
  if (status === 'pending_acceptance') {
    return 'border-border bg-app-warning-soft text-app-warning-text';
  }
  return 'border-border bg-surface-muted text-muted';
};

export const sanitizeFilenameToken = sanitizeAnalyticsFilenameToken;

export const downloadExportBlob = downloadAnalyticsExportBlob;
