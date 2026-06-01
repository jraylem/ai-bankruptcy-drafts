import { ANALYTICS_TABLE_PAGE_SIZE_OPTIONS, toAnalyticsTitleCase } from './common.helpers';

export const MOTION_SESSION_DETAIL_PAGE_SIZE_OPTIONS = ANALYTICS_TABLE_PAGE_SIZE_OPTIONS;

export const MOTION_SESSION_DETAIL_STATUS_OPTIONS = [
  { label: 'All statuses', value: '' },
  { label: 'Completed', value: 'completed' },
  { label: 'Pending', value: 'pending' },
  { label: 'Failed', value: 'failed' },
  { label: 'Cancelled', value: 'cancelled' },
];

export const MOTION_SESSION_DETAIL_CATEGORY_OPTIONS = [
  { label: 'All categories', value: '' },
  { label: 'Motions', value: 'motion' },
  { label: 'Orders', value: 'order' },
];

export const formatMotionSessionLabel = toAnalyticsTitleCase;

export const formatMotionSessionDateTime = (value: string | null) => {
  if (!value) return '--';
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return '--';

  return parsed.toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  });
};

export const formatMotionSessionDuration = (seconds: number | null) => {
  if (seconds === null || !Number.isFinite(seconds)) return '--';
  if (seconds < 60) return `${Math.round(seconds)}s`;

  const mins = Math.floor(seconds / 60);
  const remainder = Math.round(seconds % 60);
  return `${mins}m ${remainder}s`;
};

export const formatMotionSessionCosType = (cosType: string | null) => {
  if (cosType === 'WithNoticeOfHearing') return 'With Notice';
  if (cosType === 'WithoutNoticeOfHearing') return 'Without Notice';
  if (cosType === 'No') return 'No';
  return 'Not generated';
};

export const getMotionSessionStatusBadgeClass = (status: string) => {
  const normalized = status.toLowerCase();
  if (normalized === 'completed') return 'border border-border bg-app-success-soft text-app-success-text';
  if (normalized === 'pending') return 'border border-border bg-app-warning-soft text-app-warning-text';
  if (normalized === 'failed') return 'border border-border bg-app-danger-soft text-app-danger-text';
  if (normalized === 'cancelled') return 'border border-border bg-surface-muted text-muted';
  return 'border border-border bg-app-accent-soft text-app-accent-text';
};

export const getMotionSessionCategoryBadgeClass = (category: string) => {
  if (category === 'order') return 'border border-border bg-app-warning-soft text-app-warning-text';
  return 'border border-border bg-app-accent-soft text-app-accent-text';
};

export const getMotionSessionCosBadgeClass = (cosType: string | null) => {
  if (cosType === 'WithNoticeOfHearing') return 'border border-border bg-app-success-soft text-app-success-text';
  if (cosType === 'WithoutNoticeOfHearing') return 'border border-border bg-app-warning-soft text-app-warning-text';
  if (cosType === 'No') return 'border border-border bg-surface-muted text-muted';
  return 'border border-border bg-surface-muted text-subtle';
};

export const getMotionSessionCompletionRatio = (completed: number, totalAttempted: number) => {
  if (!totalAttempted) return 0;
  return Math.max(0, Math.min(100, (completed / totalAttempted) * 100));
};
