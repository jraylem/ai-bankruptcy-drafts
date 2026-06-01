import type { DashboardMotionsAnalyticsSortBy } from '@/features/analytics/types/dashboard.types';
import { ANALYTICS_TABLE_PAGE_SIZE_OPTIONS, toAnalyticsTitleCase } from './common.helpers';

export type MotionsTableSortKey = 'motion_type' | 'status' | 'created_at' | 'processing';

export const MOTIONS_PAGE_SIZE_OPTIONS = ANALYTICS_TABLE_PAGE_SIZE_OPTIONS;

export const MOTIONS_CATEGORY_OPTIONS = [
  { label: 'All categories', value: '' },
  { label: 'Motions', value: 'motion' },
  { label: 'Orders', value: 'order' },
];

export const MOTIONS_STATUS_OPTIONS = [
  { label: 'All statuses', value: '' },
  { label: 'Completed', value: 'completed' },
  { label: 'Pending', value: 'pending' },
  { label: 'Failed', value: 'failed' },
  { label: 'Cancelled', value: 'cancelled' },
];

export const MOTIONS_SOURCE_OPTIONS = [
  { label: 'All sources', value: '' },
  { label: 'Manual', value: 'manual' },
  { label: 'ECF', value: 'ecf' },
  { label: 'Google Drive', value: 'gdrive' },
  { label: 'CourtDrive', value: 'courtdrive' },
];

export const MOTIONS_COS_TYPE_OPTIONS = [
  { label: 'All COS types', value: '' },
  { label: 'With Notice', value: 'WithNoticeOfHearing' },
  { label: 'Without Notice', value: 'WithoutNoticeOfHearing' },
  { label: 'No COS', value: 'No' },
];

export const formatMotionsLabel = toAnalyticsTitleCase;

export const resolveMotionsServerSortBy = (
  sortKey: MotionsTableSortKey
): DashboardMotionsAnalyticsSortBy => {
  if (sortKey === 'status') return 'status';
  if (sortKey === 'motion_type') return 'motion_type';
  if (sortKey === 'processing') return 'processing_seconds';
  return 'created_at';
};

export const getMotionStatusBadgeClass = (status: string) => {
  const normalized = status.toLowerCase();
  if (normalized === 'completed') return 'bg-app-success-soft text-app-success-text';
  if (normalized === 'pending') return 'bg-app-warning-soft text-app-warning-text';
  if (normalized === 'failed') return 'bg-app-danger-soft text-app-danger-text';
  if (normalized === 'cancelled') return 'bg-surface-muted text-muted';
  return 'bg-app-accent-soft text-app-accent-text';
};

export const getMotionCategoryBadgeClass = (category: string) => {
  if (category.toLowerCase() === 'order') {
    return 'bg-app-warning-soft text-app-warning-text';
  }
  return 'bg-app-accent-soft text-app-accent-text';
};

export const getMotionCosBadgeClass = (cosType: string | null) => {
  if (cosType === 'WithNoticeOfHearing') return 'bg-app-success-soft text-app-success-text';
  if (cosType === 'WithoutNoticeOfHearing') return 'bg-app-warning-soft text-app-warning-text';
  if (cosType === 'No') return 'bg-surface-muted text-muted';
  return 'bg-surface-muted text-subtle';
};

export const formatMotionCosType = (cosType: string | null) => {
  if (cosType === 'WithNoticeOfHearing') return 'With Notice';
  if (cosType === 'WithoutNoticeOfHearing') return 'Without Notice';
  if (cosType === 'No') return 'No';
  return 'Not generated';
};

export const formatMotionDateTime = (value: string | null) => {
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

export const formatMotionProcessing = (seconds: number | null) => {
  if (seconds === null || !Number.isFinite(seconds)) {
    return '--';
  }

  if (seconds < 10) {
    return `${seconds.toFixed(1)}s`;
  }

  if (seconds < 60) {
    return `${Math.round(seconds)}s`;
  }

  const minutes = Math.floor(seconds / 60);
  const remainder = Math.round(seconds % 60);
  return `${minutes}m ${remainder}s`;
};
