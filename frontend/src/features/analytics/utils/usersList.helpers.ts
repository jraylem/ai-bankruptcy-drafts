import type {
  DashboardUsersAnalyticsSortBy,
  DashboardUsersAnalyticsUser,
} from '@/features/analytics/types/dashboard.types';
import type { UsersPageSizeOption, UsersTableSortKey } from '@/features/analytics/types';
import {
  ANALYTICS_TABLE_PAGE_SIZE_OPTIONS,
  downloadAnalyticsExportBlob,
  sanitizeAnalyticsFilenameToken,
} from './common.helpers';
import { formatRelativeActivityTime } from './activityFeed.helpers';

export const PAGE_SIZE_OPTIONS: UsersPageSizeOption[] = ANALYTICS_TABLE_PAGE_SIZE_OPTIONS;

export const CHART_COLORS = {
  motions: 'var(--app-accent)',
  activeUsers: 'var(--app-success-text)',
  newUsers: 'var(--app-warning-text)',
} as const;

export const resolveServerSortBy = (
  sortKey: UsersTableSortKey
): DashboardUsersAnalyticsSortBy => {
  if (sortKey === 'joined') return 'created_at';
  if (sortKey === 'cases') return 'cases_count';
  if (sortKey === 'motions') return 'motions_drafted';
  return 'last_active';
};

export const formatDate = (value: string) =>
  new Date(value).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  });

export const formatRelativeDate = (value: string | null) => {
  if (!value) {
    return 'No recent activity';
  }
  return formatRelativeActivityTime(value);
};

export const formatDuration = (seconds: number | null) => {
  if (seconds === null || !Number.isFinite(seconds)) {
    return '--';
  }

  if (seconds < 60) {
    return `${Math.round(seconds)}s`;
  }

  const minutes = Math.floor(seconds / 60);
  const remainder = Math.round(seconds % 60);
  return `${minutes}m ${remainder}s`;
};

export const formatChartDay = (value: string) =>
  new Date(`${value}T00:00:00Z`).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
  });

export const sanitizeFilenameToken = sanitizeAnalyticsFilenameToken;

export const downloadExportBlob = downloadAnalyticsExportBlob;

export const getDisplayName = (user: DashboardUsersAnalyticsUser) => {
  const trimmed = user.name?.trim();
  if (trimmed) return trimmed;
  return user.email;
};

export const getInitials = (user: DashboardUsersAnalyticsUser) => {
  const name = getDisplayName(user);
  return name
    .split(' ')
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? '')
    .join('');
};
